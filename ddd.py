import os
import glob
import json
import pandas as pd
from app_whisper_llm import incializar_audio_model, inicializar_llm, proceso_completo

def buscar_audio_por_dni(directorio_audio, dni):
    """
    Busca un archivo de audio en el directorio que contenga el DNI en su nombre.
    """
    if pd.isna(dni):
        return None
    
    # Manejamos el formato del DNI por si pandas lo lee como float
    dni_str = str(int(dni)) if isinstance(dni, float) else str(dni).strip()
    
    # Buscar archivos en el directorio que contengan el DNI
    patron = os.path.join(directorio_audio, f"*{dni_str}*.*")
    archivos = glob.glob(patron)
    
    # Filtrar solo extensiones de audio permitidas
    extensiones_validas = ['.wav', '.mp3', '.m4a', '.ogg', '.flac']
    for archivo in archivos:
        if any(archivo.lower().endswith(ext) for ext in extensiones_validas):
            return archivo
            
    return None

def comparar_y_generar_columnas(fila_excel, json_data):
    """
    Extrae los datos del JSON y realiza las comparaciones con la fila de Excel original.
    Retorna un diccionario con las nuevas columnas que se agregarán al Excel final.
    """
    nuevas_columnas = {}
    
    if not json_data:
        return nuevas_columnas
        
    try:
        # Convertir el string JSON retornado por el LLM a un diccionario de Python
        # Se limpia un poco por si el LLM incluye caracteres markdown tipo ```json
        json_clean = json_data.replace('```json', '').replace('```', '').strip()
        datos_audio = json.loads(json_clean)
    except Exception as e:
        print(f"Error parseando JSON: {e}")
        return nuevas_columnas

    # ==============================================================
    # 1. ASIGNACIÓN DE LAS COLUMNAS OBTENIDAS DEL AUDIO (Sufijo _T)
    # ==============================================================
    nuevas_columnas['DIA AUDIO CONTRATO_T'] = datos_audio.get('fecha', '')
    nuevas_columnas['CUOTA_INICIAL_T'] = datos_audio.get('couta_inicial_soles', '')
    nuevas_columnas['DEUDA_CAPITAL_T'] = datos_audio.get('deuda_capital_soles', '')
    nuevas_columnas['PLAZO_T'] = datos_audio.get('plazo_meses', '')
    nuevas_columnas['CUOTA_T'] = datos_audio.get('couta_aproximada_soles', '')
    nuevas_columnas['PRIMER VENCIMIENTO_T'] = datos_audio.get('primer_vencimiento', '')
    nuevas_columnas['NOMBRE Y APELLIDO_T'] = datos_audio.get('nombre_apellido', '')
    nuevas_columnas['DNI_T'] = datos_audio.get('dni', '')
    nuevas_columnas['CORREO_T'] = datos_audio.get('correo_electronico', '')
    nuevas_columnas['Fecha_Nacimiento_T'] = datos_audio.get('fecha_nacimiento', '')
    nuevas_columnas['TEA_T'] = datos_audio.get('TEA%', '')

    # ==============================================================
    # 2. VALIDADORES Y COMPARACIONES (CONFORME / NO CONFORME)
    # ==============================================================
    # Ejemplo de validación del DNI:
    dni_excel = str(fila_excel.get('DNI', '')).strip()
    dni_audio = str(nuevas_columnas['DNI_T']).strip()
    
    if dni_excel and dni_audio and dni_excel in dni_audio:
        nuevas_columnas['valor_12 (VALIDACION DNI)'] = 'CONFORME'
    else:
        nuevas_columnas['valor_12 (VALIDACION DNI)'] = 'NO CONFORME'

    # Ejemplo de validación de Cuota Inicial:
    cuota_excel = str(fila_excel.get('CUOTA_INICIAL', '')).strip()
    cuota_audio = str(nuevas_columnas['CUOTA_INICIAL_T']).strip()
    
    if cuota_excel and cuota_audio and cuota_excel == cuota_audio:
        nuevas_columnas['valor_2 (VALIDACION CUOTA INICIAL)'] = 'CONFORME'
    else:
        nuevas_columnas['valor_2 (VALIDACION CUOTA INICIAL)'] = 'NO CONFORME'

    # NOTA: Puedes replicar esta lógica 'if' para las demás columnas (PLAZO, CAPITAL, etc.)
    # dependiendo de los encabezados exactos de tu Excel original.

    return nuevas_columnas

def leer_excel(ruta):
    """Lee el archivo de Excel y lo retorna como un DataFrame."""
    print(f"Cargando Excel de entrada: {ruta}")
    try:
        return pd.read_excel(ruta)
    except Exception as e:
        print(f"Error al leer el Excel {ruta}. Verifica la ruta o si tienes openpyxl instalado: {e}")
        return None

def guardar_excel(lista_resultados, ruta_salida):
    """Recibe una lista de diccionarios y los guarda en un archivo Excel."""
    df_salida = pd.DataFrame(lista_resultados)
    try:
        df_salida.to_excel(ruta_salida, index=False)
        print(f"\n===========================================")
        print(f"PROCESO TERMINADO CON ÉXITO")
        print(f"Archivo guardado en: {ruta_salida}")
        print(f"===========================================")
    except Exception as e:
        print(f"Error al guardar el Excel de salida: {e}")

def procesar_fila(fila, directorio_audio, model_audio, model_llm):
    """Procesa una sola fila del Excel: busca audio, procesa IA y compara."""
    resultado_fila = fila.to_dict()
    dni = fila.get('DNI', None)
    
    if pd.isna(dni):
        print("  -> DNI nulo o no válido, omitiendo audio...")
        return resultado_fila
        
    ruta_audio = buscar_audio_por_dni(directorio_audio, dni)
    
    if ruta_audio:
        print(f"  -> Audio encontrado: {ruta_audio}")
        try:
            # Procesamos el audio con Whisper y luego extraemos JSON con el LLM
            json_str = proceso_completo(model_audio, model_llm, ruta_audio)
            
            # Comparamos los resultados con el excel
            nuevas_columnas = comparar_y_generar_columnas(fila, json_str)
            
            # Unimos ambas partes de datos
            resultado_fila.update(nuevas_columnas)
            print("  -> Extracción y validación completados.")
            
        except Exception as e:
            print(f"  -> [ERROR] Falló el procesamiento del audio: {e}")
    else:
        print(f"  -> [Aviso] No se encontró ningún audio con el DNI: {dni}")
        
    return resultado_fila

def procesar_lote_excel(ruta_excel_in, ruta_excel_out, directorio_audio):
    """
    Función orquestadora (Main): Coordina la lectura, los modelos, 
    la iteración de filas y el guardado final.
    """
    # 1. Leer Excel
    df = leer_excel(ruta_excel_in)
    if df is None:
        return

    # 2. Cargar modelos en memoria (solo 1 vez por todo el batch)
    print("Inicializando modelos...")
    model_audio = incializar_audio_model()
    model_llm = inicializar_llm()
    
    lista_resultados = []

    # 3. Iterar fila por fila procesando de forma individual
    for index, fila in df.iterrows():
        print(f"\n[{index+1}/{len(df)}] Procesando Fila - DNI esperado: {fila.get('DNI', None)}")
        fila_procesada = procesar_fila(fila, directorio_audio, model_audio, model_llm)
        lista_resultados.append(fila_procesada)
        
    # 4. Guardar archivo final
    guardar_excel(lista_resultados, ruta_excel_out)

if __name__ == "__main__":
    # CONFIGURA TUS RUTAS AQUÍ
    RUTA_EXCEL_ENTRADA = "datos_caja.xlsx"
    RUTA_EXCEL_SALIDA = "datos_salida_validados.xlsx"
    DIRECTORIO_AUDIOS = "./mis_audios" 
    
    procesar_lote_excel(RUTA_EXCEL_ENTRADA, RUTA_EXCEL_SALIDA, DIRECTORIO_AUDIOS)
