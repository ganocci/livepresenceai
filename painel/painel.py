"""
LivePresenceAI - Painel do computador (servidor e/ou sala).

Uma tela unica para quem nao e da area de TI:
  - Servidor: liga/desliga o backend (API + app web), mostra se o banco esta no ar, abre o app e mostra os
    enderecos para os celulares e o certificado HTTPS a instalar neles.
  - Esta sala: escolhe a sala e a camera (com teste de imagem) e liga/desliga o reconhecimento.
  - Iniciar com o Windows: liga tudo sozinho ao entrar no Windows (atalho na pasta Inicializar).
  - Registros: ultimas linhas do servidor e do modulo da sala, para suporte.

Uso: pythonw painel.py [--auto]   (--auto: abre minimizado e liga o que estiver marcado como ativo)
"""
import os
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import configuracao as cfg  # noqa: E402
import servicos  # noqa: E402

AZUL, FUNDO, CARTAO, TEXTO, CINZA = "#0866FF", "#F0F2F5", "#FFFFFF", "#050505", "#65676B"
VERDE, AMBAR, VERMELHO = "#31A24C", "#E59400", "#E41E3F"
ATALHO_INICIAR = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs",
                              "Startup", "LivePresenceAI.lnk")


class Painel:
    def __init__(self, raiz: tk.Tk, automatico: bool):
        self.raiz = raiz
        self.config = cfg.carregar()
        self.servidor = servicos.Servico("servidor")
        self.sala = servicos.Servico("sala")
        self.salas = []
        self._montar()
        self._atualizar_estado(periodico=True)
        if automatico:
            self.raiz.iconify()
            self.raiz.after(500, self.ligar_tudo)

    # ---------------------- interface ----------------------

    def _cartao(self, pai, titulo: str, subtitulo: str) -> tk.Frame:
        moldura = tk.Frame(pai, bg=CARTAO, padx=16, pady=12, highlightthickness=0)
        moldura.pack(fill="x", padx=14, pady=6)
        tk.Label(moldura, text=titulo, bg=CARTAO, fg=TEXTO, font=("Segoe UI", 13, "bold")).pack(anchor="w")
        tk.Label(moldura, text=subtitulo, bg=CARTAO, fg=CINZA, font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 8))
        return moldura

    def _status(self, pai, texto: str):
        linha = tk.Frame(pai, bg=CARTAO)
        linha.pack(fill="x", pady=2)
        bolinha = tk.Label(linha, text="●", bg=CARTAO, fg=CINZA, font=("Segoe UI", 12))
        bolinha.pack(side="left")
        rotulo = tk.Label(linha, text=texto, bg=CARTAO, fg=TEXTO, font=("Segoe UI", 10))
        rotulo.pack(side="left", padx=6)
        return bolinha, rotulo

    def _montar(self) -> None:
        r = self.raiz
        r.title("LivePresenceAI — Painel")
        r.configure(bg=FUNDO)
        r.geometry("760x780")
        r.minsize(680, 640)
        estilo = ttk.Style()
        estilo.theme_use("clam")
        estilo.configure("Azul.TButton", background=AZUL, foreground="white", font=("Segoe UI", 10, "bold"),
                         padding=(14, 6), borderwidth=0)
        estilo.map("Azul.TButton", background=[("active", "#0A58D0"), ("disabled", "#9DBEF5")])
        estilo.configure("Cinza.TButton", background="#E4E6EB", foreground=TEXTO, font=("Segoe UI", 10),
                         padding=(12, 6), borderwidth=0)
        estilo.map("Cinza.TButton", background=[("active", "#D8DADF")])

        topo = tk.Frame(r, bg=CARTAO, padx=16, pady=10)
        topo.pack(fill="x")
        tk.Label(topo, text="livepresence", bg=CARTAO, fg=AZUL, font=("Segoe UI", 20, "bold")).pack(side="left")
        tk.Label(topo, text="AI", bg=CARTAO, fg="#7B61FF", font=("Segoe UI", 20, "bold")).pack(side="left")
        tk.Label(topo, text="Painel deste computador", bg=CARTAO, fg=CINZA, font=("Segoe UI", 10)).pack(
            side="left", padx=10, pady=(8, 0))

        # Servidor
        c = self._cartao(r, "Servidor", "Banco de dados, API e app do professor. Deixe ligado durante as aulas.")
        self.bola_banco, self.txt_banco = self._status(c, "Banco de dados")
        self.bola_srv, self.txt_srv = self._status(c, "Servidor")
        botoes = tk.Frame(c, bg=CARTAO)
        botoes.pack(fill="x", pady=(8, 4))
        self.bt_srv = ttk.Button(botoes, text="Ligar servidor", style="Azul.TButton", command=self.alternar_servidor)
        self.bt_srv.pack(side="left")
        ttk.Button(botoes, text="Abrir o app", style="Cinza.TButton", command=self.abrir_app).pack(side="left", padx=6)
        ttk.Button(botoes, text="Celulares e outras salas", style="Cinza.TButton",
                   command=self.abrir_conexoes).pack(side="left")
        self.txt_enderecos = tk.Label(c, text="", bg=CARTAO, fg=CINZA, font=("Segoe UI", 9), justify="left")
        self.txt_enderecos.pack(anchor="w", pady=(6, 0))

        # Sala
        c = self._cartao(r, "Esta sala", "Câmera e reconhecimento facial deste computador.")
        linha = tk.Frame(c, bg=CARTAO)
        linha.pack(fill="x", pady=2)
        tk.Label(linha, text="Sala:", bg=CARTAO, width=8, anchor="w", font=("Segoe UI", 10)).pack(side="left")
        self.cb_sala = ttk.Combobox(linha, state="readonly", width=34)
        self.cb_sala.pack(side="left")
        self.cb_sala.bind("<<ComboboxSelected>>", self._sala_escolhida)
        ttk.Button(linha, text="Atualizar lista", style="Cinza.TButton", command=self.carregar_salas).pack(side="left", padx=6)
        linha = tk.Frame(c, bg=CARTAO)
        linha.pack(fill="x", pady=2)
        tk.Label(linha, text="Câmera:", bg=CARTAO, width=8, anchor="w", font=("Segoe UI", 10)).pack(side="left")
        self.cb_camera = ttk.Combobox(linha, state="readonly", width=12,
                                      values=[f"Câmera {self.config['sala']['camera']}"])
        self.cb_camera.current(0)
        self.cb_camera.pack(side="left")
        self.cb_camera.bind("<<ComboboxSelected>>", self._camera_escolhida)
        ttk.Button(linha, text="Procurar câmeras", style="Cinza.TButton", command=self.procurar_cameras).pack(side="left", padx=6)
        ttk.Button(linha, text="Testar imagem", style="Cinza.TButton", command=self.testar_camera).pack(side="left")
        self.var_video = tk.BooleanVar(value=self.config["sala"].get("mostrar_video", True))
        tk.Checkbutton(c, text="Mostrar o vídeo com os nomes durante a aula", variable=self.var_video, bg=CARTAO,
                       activebackground=CARTAO, command=self._video_alterado).pack(anchor="w", pady=(4, 0))
        self.bola_sala, self.txt_sala = self._status(c, "Reconhecimento desligado")
        self.bt_sala = ttk.Button(c, text="Ligar reconhecimento", style="Azul.TButton", command=self.alternar_sala)
        self.bt_sala.pack(anchor="w", pady=(6, 0))

        # Geral
        geral = tk.Frame(r, bg=FUNDO)
        geral.pack(fill="x", padx=14, pady=6)
        ttk.Button(geral, text="Ligar tudo", style="Azul.TButton", command=self.ligar_tudo).pack(side="left")
        ttk.Button(geral, text="Desligar tudo", style="Cinza.TButton", command=self.desligar_tudo).pack(side="left", padx=6)
        self.var_windows = tk.BooleanVar(value=os.path.exists(ATALHO_INICIAR))
        tk.Checkbutton(geral, text="Iniciar com o Windows", variable=self.var_windows, bg=FUNDO,
                       activebackground=FUNDO, command=self.alternar_inicio_windows).pack(side="left", padx=12)

        # Registros
        abas = ttk.Notebook(r)
        abas.pack(fill="both", expand=True, padx=14, pady=(4, 12))
        self.log_srv = ScrolledText(abas, height=8, font=("Consolas", 9), wrap="none")
        self.log_sala = ScrolledText(abas, height=8, font=("Consolas", 9), wrap="none")
        abas.add(self.log_srv, text="Registro do servidor")
        abas.add(self.log_sala, text="Registro da sala")

        r.protocol("WM_DELETE_WINDOW", self.fechar)
        self._preencher_sala_salva()
        self.raiz.after(800, self.carregar_salas)

    # ---------------------- servidor ----------------------

    def alternar_servidor(self) -> None:
        if self.servidor.rodando:
            self.servidor.parar()
        else:
            erro = servicos.iniciar_servidor(self.servidor, self.config)
            if erro:
                messagebox.showerror("LivePresenceAI", erro)
        self._atualizar_estado()

    def abrir_app(self) -> None:
        webbrowser.open(cfg.endereco_local(self.config) + "/app/")

    def abrir_conexoes(self) -> None:
        """Como os celulares e os computadores de outras salas chegam a este servidor."""
        janela = tk.Toplevel(self.raiz)
        janela.title("Celulares e outras salas")
        janela.configure(bg=CARTAO, padx=18, pady=14)
        janela.resizable(False, False)
        janela.transient(self.raiz)

        def titulo(texto):
            tk.Label(janela, text=texto, bg=CARTAO, fg=TEXTO, font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(8, 2))

        def texto(conteudo):
            tk.Label(janela, text=conteudo, bg=CARTAO, fg=CINZA, font=("Segoe UI", 9), justify="left",
                     wraplength=470).pack(anchor="w")

        titulo("App Android")
        texto("Instale o app pelo navegador do celular em <endereço>/android. Com o celular no mesmo Wi-Fi deste "
              "computador, o app encontra o servidor sozinho: não é preciso digitar o endereço nem instalar "
              "certificado.")
        titulo("Navegador do celular ou de outro computador")
        texto("Para usar o app pelo navegador, o aparelho precisa confiar no certificado HTTPS: instale o arquivo "
              "ca.crt como certificado de autoridade (CA). Android: Configurações > Segurança > Criptografia e "
              "credenciais > Instalar certificado > Certificado de CA.")
        ttk.Button(janela, text="Abrir a pasta do certificado", style="Cinza.TButton",
                   command=self._abrir_pasta_certificado).pack(anchor="w", pady=(6, 0))
        titulo("Computador de outra sala")
        texto("No instalador do outro computador, escolha \"Só a câmera de uma sala\". Ele encontra este servidor "
              "na rede e pede apenas esta chave:")
        chave = cfg.chave_da_sala(self.config) if self.config["servidor"]["ativo"] else "(este computador não é o servidor)"
        campo = ttk.Entry(janela, width=58)
        campo.insert(0, chave)
        campo.configure(state="readonly")
        campo.pack(anchor="w", pady=(6, 0))

        def copiar():
            self.raiz.clipboard_clear()
            self.raiz.clipboard_append(chave)
            bt_copiar.configure(text="Copiada")
        bt_copiar = ttk.Button(janela, text="Copiar chave", style="Azul.TButton", command=copiar)
        bt_copiar.pack(anchor="w", pady=(6, 0))
        ttk.Button(janela, text="Fechar", style="Cinza.TButton", command=janela.destroy).pack(anchor="e", pady=(12, 0))

    def _abrir_pasta_certificado(self) -> None:
        servicos.preparar_certificado()
        os.makedirs(cfg.PASTA_CERTIFICADOS, exist_ok=True)
        os.startfile(cfg.PASTA_CERTIFICADOS)

    # ---------------------- sala ----------------------

    def _preencher_sala_salva(self) -> None:
        sala = self.config["sala"]
        if sala.get("sala_nome"):
            self.cb_sala["values"] = [sala["sala_nome"]]
            self.cb_sala.current(0)

    def carregar_salas(self) -> None:
        def tarefa():
            try:
                salas = servicos.listar_salas(self.config)
                self.raiz.after(0, lambda: self._mostrar_salas(salas))
            except Exception:
                self.raiz.after(0, lambda: self._mostrar_salas(None))
        threading.Thread(target=tarefa, daemon=True).start()

    def _mostrar_salas(self, salas) -> None:
        if salas is None:
            if not self.cb_sala["values"]:
                self.cb_sala.set("Servidor fora do ar: ligue-o e clique em Atualizar lista")
            return
        self.salas = salas
        if not salas:
            self.cb_sala.set("Nenhuma sala cadastrada (cadastre em Administração, no app)")
            self.cb_sala["values"] = []
            return
        self.cb_sala["values"] = [s["nome"] for s in salas]
        atual = self.config["sala"].get("sala_id")
        for i, s in enumerate(salas):
            if s["id"] == atual:
                self.cb_sala.current(i)

    def _sala_escolhida(self, _evento=None) -> None:
        indice = self.cb_sala.current()
        if 0 <= indice < len(self.salas):
            sala = self.salas[indice]
            self.config["sala"].update({"sala_id": sala["id"], "sala_nome": sala["nome"], "ativo": True})
            cfg.salvar(self.config)

    def procurar_cameras(self) -> None:
        self.cb_camera.set("Procurando…")

        def tarefa():
            cameras = servicos.listar_cameras()
            self.raiz.after(0, lambda: self._mostrar_cameras(cameras))
        threading.Thread(target=tarefa, daemon=True).start()

    def _mostrar_cameras(self, cameras) -> None:
        if not cameras:
            self.cb_camera.set("Nenhuma câmera")
            messagebox.showwarning("LivePresenceAI", "Nenhuma câmera respondeu. Confira o cabo e se outro programa "
                                                     "(Teams, Zoom, Câmera do Windows) está usando a câmera.")
            return
        self.cb_camera["values"] = [f"Câmera {i}" for i in cameras]
        atual = self.config["sala"]["camera"]
        self.cb_camera.current(cameras.index(atual) if atual in cameras else 0)
        self._camera_escolhida()

    def _camera_escolhida(self, _evento=None) -> None:
        texto = self.cb_camera.get()
        if texto.startswith("Câmera "):
            self.config["sala"]["camera"] = int(texto.split()[1])
            cfg.salvar(self.config)

    def _video_alterado(self) -> None:
        self.config["sala"]["mostrar_video"] = self.var_video.get()
        cfg.salvar(self.config)

    def testar_camera(self) -> None:
        if self.sala.rodando:
            messagebox.showinfo("LivePresenceAI", "Desligue o reconhecimento antes de testar a câmera.")
            return
        servicos.testar_camera(self.config["sala"]["camera"])

    def alternar_sala(self) -> None:
        if self.sala.rodando:
            self.sala.parar()
        else:
            erro = servicos.iniciar_sala(self.sala, self.config)
            if erro:
                messagebox.showwarning("LivePresenceAI", erro)
        self._atualizar_estado()

    # ---------------------- geral ----------------------

    def ligar_tudo(self) -> None:
        if self.config["servidor"].get("ativo", True) and not self.servidor.rodando:
            erro = servicos.iniciar_servidor(self.servidor, self.config)
            if erro:
                messagebox.showerror("LivePresenceAI", erro)
        if self.config["sala"].get("ativo") and self.config["sala"].get("sala_id") is not None and not self.sala.rodando:
            # Espera o servidor responder antes de ligar a sala (o modulo tambem tenta de novo sozinho)
            self.raiz.after(4000, lambda: servicos.iniciar_sala(self.sala, self.config))
        self._atualizar_estado()

    def desligar_tudo(self) -> None:
        self.sala.parar()
        self.servidor.parar()
        self._atualizar_estado()

    def alternar_inicio_windows(self) -> None:
        pythonw = cfg.python_do_ambiente("backend", janela=True)
        if self.var_windows.get():
            if not pythonw:
                messagebox.showerror("LivePresenceAI", "Ambiente do servidor não encontrado.")
                self.var_windows.set(False)
                return
            script = os.path.abspath(__file__)
            comando = (
                f"$a=(New-Object -ComObject WScript.Shell).CreateShortcut('{ATALHO_INICIAR}');"
                f"$a.TargetPath='{pythonw}';$a.Arguments='\"{script}\" --auto';"
                f"$a.WorkingDirectory='{os.path.dirname(script)}';$a.Save()"
            )
            subprocess.run(["powershell", "-NoProfile", "-Command", comando], creationflags=servicos.SEM_JANELA)
        elif os.path.exists(ATALHO_INICIAR):
            os.remove(ATALHO_INICIAR)
        self.config["iniciar_com_windows"] = self.var_windows.get()
        cfg.salvar(self.config)

    def fechar(self) -> None:
        if self.servidor.rodando or self.sala.rodando:
            if not messagebox.askyesno("LivePresenceAI", "Fechar o painel desliga o servidor e o reconhecimento "
                                                         "deste computador. Deseja fechar?"):
                return
        self.desligar_tudo()
        self.raiz.destroy()

    # ---------------------- estado (a cada 2 s) ----------------------

    def _atualizar_estado(self, periodico: bool = False) -> None:
        """Consulta banco e servidor fora da interface; so a chamada periodica agenda a proxima (2 s)."""
        def tarefa():
            banco = servicos.banco_aceitando(self.config)
            servidor = servicos.servidor_respondendo(self.config)
            self.raiz.after(0, lambda: self._mostrar_estado(banco, servidor, periodico))
        threading.Thread(target=tarefa, daemon=True).start()

    def _mostrar_estado(self, banco: bool, servidor: bool, periodico: bool = False) -> None:
        self.bola_banco.config(fg=VERDE if banco else VERMELHO)
        self.txt_banco.config(text="Banco de dados no ar" if banco else "Banco de dados fora do ar (PostgreSQL)")
        if servidor:
            self.bola_srv.config(fg=VERDE)
            self.txt_srv.config(text=f"Servidor no ar em {cfg.endereco_local(self.config)}")
        elif self.servidor.rodando:
            self.bola_srv.config(fg=AMBAR)
            self.txt_srv.config(text="Servidor iniciando…")
        else:
            self.bola_srv.config(fg=CINZA)
            self.txt_srv.config(text="Servidor desligado")
        self.bt_srv.config(text="Desligar servidor" if self.servidor.rodando else "Ligar servidor")
        enderecos = servicos.enderecos_para_celulares(self.config)
        self.txt_enderecos.config(
            text=("Nos celulares, use o endereço: " + "  ou  ".join(enderecos)
                  + f"\nApp Android para instalar: {enderecos[0]}/android") if enderecos else "")
        if self.sala.rodando:
            self.bola_sala.config(fg=VERDE)
            self.txt_sala.config(text=f"Reconhecimento ligado na {self.config['sala'].get('sala_nome') or 'sala'}")
        else:
            self.bola_sala.config(fg=CINZA)
            self.txt_sala.config(text="Reconhecimento desligado")
        self.bt_sala.config(text="Desligar reconhecimento" if self.sala.rodando else "Ligar reconhecimento")
        for caixa, servico in ((self.log_srv, self.servidor), (self.log_sala, self.sala)):
            no_fim = caixa.yview()[1] > 0.98
            caixa.delete("1.0", "end")
            caixa.insert("end", servico.ultimas_linhas())
            if no_fim:
                caixa.see("end")
        if periodico:
            self.raiz.after(2000, lambda: self._atualizar_estado(periodico=True))


def main() -> None:
    raiz = tk.Tk()
    Painel(raiz, automatico="--auto" in sys.argv)
    raiz.mainloop()


if __name__ == "__main__":
    main()
