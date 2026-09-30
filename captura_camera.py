"""
LivePresenceAI - Captura de Camera USB Generica (Dia 1)
Etapa isolada da camada fisica/pipeline de visao computacional: apenas abre
a webcam e exibe o video, sem deteccao ainda (YOLOv8/InsightFace entram depois).

Uso: python captura_camera.py
Pressione 'q' na janela de video para encerrar.
"""
import cv2

INDICE_CAMERA = 0  # 0 = primeira webcam USB detectada pelo sistema. Ajustar se houver mais de uma.
LARGURA = 640
ALTURA = 480


def iniciar_captura():
    captura = cv2.VideoCapture(INDICE_CAMERA)
    captura.set(cv2.CAP_PROP_FRAME_WIDTH, LARGURA)
    captura.set(cv2.CAP_PROP_FRAME_HEIGHT, ALTURA)

    if not captura.isOpened():
        print(f"Não foi possível abrir a câmera no índice {INDICE_CAMERA}. "
              f"Verifique se está conectada ou tente outro índice (1, 2...).")
        return

    print("Câmera aberta com sucesso. Pressione 'q' na janela para sair.")

    while True:
        sucesso, frame = captura.read()
        if not sucesso:
            print("Falha ao ler o frame da câmera.")
            break

        # Ponto de extensão futuro: aqui entrará a chamada ao YOLOv8 para
        # detectar rostos no frame, depois InsightFace + Liveness Detection,
        # antes de enviar o resultado ao backend via POST /sessoes/{id}/reconhecimento.
        cv2.putText(
            frame,
            "LivePresenceAI - Captura ativa (protótipo Dia 1)",
            (10, 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 0),
            2,
        )

        cv2.imshow("LivePresenceAI - Câmera", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    captura.release()
    cv2.destroyAllWindows()
    print("Captura encerrada.")


if __name__ == "__main__":
    iniciar_captura()
