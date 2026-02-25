import os
import time
import threading
import concurrent.futures
import psutil
from llama_cpp import Llama

# ─────────────────────────────────────────────────────────────
# Config automática basada en hardware disponible
# ─────────────────────────────────────────────────────────────
CPU_CORES        = os.cpu_count() or 16
RAM_LIBRE_GB     = psutil.virtual_memory().available / (1024 ** 3)
RAM_POR_SLOT_GB  = 2.0   # Qwen3-1.7B Q8 ≈ 2 GB por slot de 4096 tokens
N_PARALLEL       = min(CPU_CORES, max(1, int(RAM_LIBRE_GB // RAM_POR_SLOT_GB)))
N_CTX_TOTAL      = 4096 * N_PARALLEL


def _fmt(seg: float) -> str:
    m, s = int(seg // 60), int(seg % 60)
    return f"{m}:{s:02d}"


# ─────────────────────────────────────────────────────────────
# Inicialización
# ─────────────────────────────────────────────────────────────

def inicializar_llm() -> Llama:
    model_path = r"D:\0.1 Modelos\Qwen3-1.7B-Q8_0.gguf"
    print(f"\n{'='*60}")
    print(f"  CPU cores     : {CPU_CORES}")
    print(f"  RAM libre     : {RAM_LIBRE_GB:.1f} GB")
    print(f"  Slots paralelos: {N_PARALLEL}")
    print(f"  n_ctx total   : {N_CTX_TOTAL}")
    print(f"{'='*60}\n")
    print("Cargando LLM...")
    t0 = time.time()
    llm = Llama(
        model_path,
        n_ctx=N_CTX_TOTAL,
        n_threads=CPU_CORES,
        n_parallel=N_PARALLEL,
        verbose=False,
    )
    print(f"LLM listo en {_fmt(time.time() - t0)}\n")
    return llm


# ─────────────────────────────────────────────────────────────
# Inferencia
# ─────────────────────────────────────────────────────────────

def _responder(idx: int, texto: str, llm: Llama) -> dict:
    messages = [
        {"role": "system", "content": "Eres un asistente útil. Responde de forma concisa."},
        {"role": "user",   "content": texto},
    ]
    t0 = time.time()
    print(f"  [{idx+1}] Iniciando...")
    respuesta = llm.create_chat_completion(messages=messages)
    contenido = respuesta["choices"][0]["message"]["content"]
    print(f"  [{idx+1}] Listo en {_fmt(time.time() - t0)}")
    return {"idx": idx, "texto": texto, "respuesta": contenido}


def procesar_en_paralelo(textos: list[str], llm: Llama) -> list[dict]:
    total = len(textos)
    t0 = time.time()
    print(f"\n{'='*60}")
    print(f"  Procesando {total} solicitudes en paralelo...")
    print(f"{'='*60}\n")

    resultados = [None] * total
    lock = threading.Lock()

    def _worker(idx: int, texto: str):
        try:
            res = _responder(idx, texto, llm)
        except Exception as exc:
            res = {"idx": idx, "texto": texto, "respuesta": None, "error": str(exc)}
        with lock:
            resultados[idx] = res

    # ThreadPoolExecutor con N_PARALLEL workers — coincide con los slots del LLM
    # Si hay más textos que slots, la cola es automática y todos se procesan
    with concurrent.futures.ThreadPoolExecutor(max_workers=N_PARALLEL) as ex:
        concurrent.futures.wait([ex.submit(_worker, i, t) for i, t in enumerate(textos)])

    print(f"\n  Tiempo total: {_fmt(time.time() - t0)}")
    return resultados


# ─────────────────────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────────────────────

def _mostrar_resultados(resultados: list[dict]):
    print(f"\n{'='*60}  RESULTADOS  {'='*60}")
    for res in resultados:
        if res is None:
            print("\n[?] Sin resultado (error interno)")
            continue
        entrada = res['texto'][:80] + ('...' if len(res['texto']) > 80 else '')
        print(f"\n[{res['idx']+1}] Entrada : {entrada}")
        if res.get('error'):
            print(f"     ERROR   : {res['error']}")
        else:
            print(f"     Respuesta: {res['respuesta']}")
    print(f"\n{'='*60}")


def menu(llm: Llama):
    while True:
        print(f"\n{'='*60}")
        print("  MENU - LLM PARALELO")
        print(f"{'='*60}")
        print("1. Enviar textos (separados por coma)")
        print("2. Salir")
        print(f"{'='*60}")

        op = input("Opcion: ").strip()

        if op == "2":
            print("Saliendo...")
            break

        if op == "1":
            entrada = input("Textos (separados por coma): ")
            textos = [t.strip() for t in entrada.split(",") if t.strip()]
            if not textos:
                print("  X Sin textos validos")
                continue
            resultados = procesar_en_paralelo(textos, llm)
            _mostrar_resultados(resultados)
        else:
            print("  X Opcion invalida")


# ─────────────────────────────────────────────────────────────
# Entrada
# ─────────────────────────────────────────────────────────────

def main():
    llm = inicializar_llm()
    menu(llm)
    print("\nProceso finalizado")


if __name__ == "__main__":
    main()
