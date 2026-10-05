"""
LivePresenceAI - Certificados para HTTPS na rede local, sem internet.

Gera uma autoridade certificadora (CA) propria da instalacao e um certificado do servidor assinado por ela,
valido para localhost, 127.0.0.1, o nome do computador e os IPs da rede local. Os navegadores e celulares
passam a confiar no servidor depois que a CA (ca.crt) e instalada neles uma vez; sem isso, mostram o aviso
de conexao nao segura. HTTPS e necessario para a camera funcionar no navegador fora do localhost e para
proteger senhas e vetores faciais na rede.

Uso: python certificado_local.py <pasta>   (cria ou atualiza <pasta>/ca.crt, ca.key, servidor.crt, servidor.key)
"""
import datetime
import ipaddress
import os
import socket
import sys
from typing import List

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def ips_locais() -> List[str]:
    """IPv4 da maquina na rede local (alem de 127.0.0.1)."""
    ips = {"127.0.0.1"}
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    try:  # IP usado para sair para a rede (sem enviar nada)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ips.add(s.getsockname()[0])
    except OSError:
        pass
    return sorted(ips)


def _salvar(caminho: str, conteudo: bytes) -> None:
    with open(caminho, "wb") as arquivo:
        arquivo.write(conteudo)


def _chave() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _pem_chave(chave) -> bytes:
    return chave.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                               serialization.NoEncryption())


def garantir_ca(pasta: str):
    """Carrega a CA da instalacao ou cria uma nova (valida por 10 anos)."""
    crt, key = os.path.join(pasta, "ca.crt"), os.path.join(pasta, "ca.key")
    if os.path.exists(crt) and os.path.exists(key):
        with open(crt, "rb") as f:
            certificado = x509.load_pem_x509_certificate(f.read())
        with open(key, "rb") as f:
            chave = serialization.load_pem_private_key(f.read(), password=None)
        if _tem_extensao(certificado, x509.SubjectKeyIdentifier):
            return certificado, chave
        # CA gerada por versao anterior, sem o identificador de chave exigido na verificacao estrita: refaz
    chave = _chave()
    nome = x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "LivePresenceAI"),
        x509.NameAttribute(NameOID.COMMON_NAME, f"LivePresenceAI CA local ({socket.gethostname()})"),
    ])
    agora = datetime.datetime.now(datetime.timezone.utc)
    certificado = (
        x509.CertificateBuilder().subject_name(nome).issuer_name(nome).public_key(chave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(agora - datetime.timedelta(days=1))
        .not_valid_after(agora + datetime.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True,
                                     content_commitment=False, key_encipherment=False, data_encipherment=False,
                                     key_agreement=False, encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(chave.public_key()), critical=False)
        .sign(chave, hashes.SHA256())
    )
    _salvar(key, _pem_chave(chave))
    _salvar(crt, certificado.public_bytes(serialization.Encoding.PEM))
    return certificado, chave


def _tem_extensao(certificado, tipo) -> bool:
    try:
        certificado.extensions.get_extension_for_class(tipo)
        return True
    except x509.ExtensionNotFound:
        return False


def nomes_do_certificado(caminho: str) -> List[str]:
    """Nomes e IPs cobertos por um certificado de servidor existente."""
    with open(caminho, "rb") as f:
        certificado = x509.load_pem_x509_certificate(f.read())
    san = certificado.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    return sorted(str(n.value) for n in san)


def garantir_certificado_servidor(pasta: str) -> str:
    """
    Cria o certificado do servidor, ou recria se os IPs da maquina mudaram ou se faltam menos de 30 dias
    para vencer. Devolve o caminho de servidor.crt.
    """
    os.makedirs(pasta, exist_ok=True)
    ca, chave_ca = garantir_ca(pasta)
    crt, key = os.path.join(pasta, "servidor.crt"), os.path.join(pasta, "servidor.key")
    host = socket.gethostname()
    desejados = sorted({"localhost", host, *ips_locais()})
    if os.path.exists(crt) and os.path.exists(key):
        with open(crt, "rb") as f:
            atual = x509.load_pem_x509_certificate(f.read())
        restante = atual.not_valid_after_utc - datetime.datetime.now(datetime.timezone.utc)
        if (nomes_do_certificado(crt) == desejados and restante > datetime.timedelta(days=30)
                and atual.issuer == ca.subject and _tem_extensao(atual, x509.AuthorityKeyIdentifier)):
            return crt
    chave = _chave()
    agora = datetime.datetime.now(datetime.timezone.utc)
    nomes = [x509.DNSName("localhost"), x509.DNSName(host)]
    nomes += [x509.IPAddress(ipaddress.ip_address(ip)) for ip in ips_locais()]
    certificado = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host)]))
        .issuer_name(ca.subject).public_key(chave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(agora - datetime.timedelta(days=1))
        .not_valid_after(agora + datetime.timedelta(days=825))  # limite aceito por iOS/macOS
        .add_extension(x509.SubjectAlternativeName(nomes), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.KeyUsage(digital_signature=True, key_encipherment=True, key_cert_sign=False,
                                     crl_sign=False, content_commitment=False, data_encipherment=False,
                                     key_agreement=False, encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(chave.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(chave_ca.public_key()), critical=False)
        .sign(chave_ca, hashes.SHA256())
    )
    _salvar(key, _pem_chave(chave))
    _salvar(crt, certificado.public_bytes(serialization.Encoding.PEM))
    return crt


if __name__ == "__main__":
    destino = sys.argv[1] if len(sys.argv) > 1 else "certificados"
    caminho = garantir_certificado_servidor(destino)
    print(f"Certificado: {caminho}")
    print("Valido para:", ", ".join(nomes_do_certificado(caminho)))
    print(f"Instale {os.path.join(destino, 'ca.crt')} nos celulares e navegadores para confiar no servidor.")
