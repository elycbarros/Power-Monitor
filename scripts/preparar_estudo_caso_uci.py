#!/usr/bin/env python3
"""Script de obtenção, saneamento e preparação do estudo de caso real UCI.

Dataset de Referência:
Individual Household Electric Power Consumption (UCI Machine Learning Repository)
Autores: Georges Hebrail & Alice Berard (EDF R&D, 2006).
DOI: 10.24432/C58K54
Licença: Creative Commons Attribution 4.0 International (CC BY 4.0).

Regra de Seleção do Recorte:
Primeiro mês civil completo (dia 01 00:00 ao último dia 23:59) com 100% de
disponibilidade metrológica, 0 registros ausentes ('?') e 0 duplicatas:
Mês Selecionado: Maio de 2007 (2007-05), com 44.640 minutos e 744 horas completas.

Política Conservadora de Agregação Horária:
- Uma hora só é gerada se possuir exatamente 60 medições de minuto válidas,
  sem duplicatas e com potência ativa finita e não negativa (P >= 0).
- Horas incompletas ficam estritamente ausentes no conjunto derivado (sem preenchimento por zero).
- A potência média horária é a média aritmética dos 60 minutos: P_hora = (1/60) * sum(P_min).
- A energia horária resultante (P_hora * 1.0h) é matematicamente equivalente à soma das energias
  minuto a minuto: sum(P_min * 1/60).
"""

import argparse
import csv
from collections import defaultdict
from datetime import datetime
import math
from pathlib import Path
import urllib.request
import zipfile
from typing import Dict, Any, List, Tuple, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUT = BASE_DIR / "data" / "medicoes_uci_2007_05.csv"
UCI_ZIP_URL = "https://archive.ics.uci.edu/static/public/235/individual+household+electric+power+consumption.zip"
LOCAL_RAW_DIR = Path("/tmp/uci_raw")


def baixar_e_extrair_dataset(destino_dir: Path) -> Path:
    """Baixa o arquivo ZIP oficial da UCI se necessário e extrai o TXT de medições."""
    destino_dir.mkdir(parents=True, exist_ok=True)
    txt_path = destino_dir / "household_power_consumption.txt"
    if txt_path.exists() and txt_path.stat().st_size > 100 * 1024 * 1024:
        print(f"-> Arquivo bruto já existente em: {txt_path} ({txt_path.stat().st_size / (1024*1024):.1f} MB)")
        return txt_path

    zip_path = destino_dir / "power.zip"
    print(f"-> Baixando dataset oficial da UCI ({UCI_ZIP_URL})...")
    urllib.request.urlretrieve(UCI_ZIP_URL, zip_path)
    print(f"   Download concluído ({zip_path.stat().st_size / (1024*1024):.1f} MB). Extraindo...")

    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(destino_dir)

    if not txt_path.exists():
        raise FileNotFoundError(f"Arquivo 'household_power_consumption.txt' não encontrado após extrair {zip_path}")

    print(f"-> Extração finalizada: {txt_path.name} ({txt_path.stat().st_size / (1024*1024):.1f} MB)")
    return txt_path


def processar_mes_uci(
    arquivo_txt: Path,
    ano: int = 2007,
    mes: int = 5,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Processa o mês civil selecionado em streaming linha por linha.

    Aplica a política conservadora de agregação horária e retorna os registros
    horários derivados e o relatório de auditoria metrológica.
    """
    mes_str = f"{mes:02d}"
    ano_str = str(ano)

    dias_no_mes = 31 if mes in (1, 3, 5, 7, 8, 10, 12) else (30 if mes != 2 else (29 if ano % 4 == 0 else 28))
    minutos_esperados_mes = dias_no_mes * 24 * 60
    horas_esperadas_mes = dias_no_mes * 24

    # Contadores de auditoria
    minutos_encontrados = 0
    minutos_ausentes_ou_nulos = 0
    minutos_invalidos = 0
    minutos_duplicados = 0
    minutos_validos = 0

    # Armazenamento temporário de minutos agrupados por hora
    # chave: 'YYYY-MM-DD HH:00' -> lista de potências (kW)
    horas_dict = defaultdict(list)
    minutos_vistos = set()

    print(f"-> Lendo arquivo bruto para o recorte {ano_str}-{mes_str}...")
    with open(arquivo_txt, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f, delimiter=";")
        header = next(reader, None)
        if not header:
            raise ValueError("Arquivo TXT vazio.")

        for row in reader:
            if not row or len(row) < 3:
                continue

            date_raw = row[0].strip()  # dd/mm/yyyy
            parts = date_raw.split("/")
            if len(parts) != 3:
                continue

            d, m, y = parts[0], parts[1].zfill(2), parts[2]
            if y != ano_str or m != mes_str:
                continue

            time_raw = row[1].strip()  # hh:mm:ss
            t_parts = time_raw.split(":")
            if len(t_parts) != 3:
                continue

            hh, mm = t_parts[0].zfill(2), t_parts[1].zfill(2)
            timestamp_minuto = f"{y}-{m}-{d.zfill(2)} {hh}:{mm}"
            hora_chave = f"{y}-{m}-{d.zfill(2)} {hh}:00"

            minutos_encontrados += 1

            if timestamp_minuto in minutos_vistos:
                minutos_duplicados += 1
                continue
            minutos_vistos.add(timestamp_minuto)

            pwr_raw = row[2].strip()
            if pwr_raw in ("?", "", "NA", "null"):
                minutos_ausentes_ou_nulos += 1
                continue

            try:
                pwr_val = float(pwr_raw)
                if not math.isfinite(pwr_val) or pwr_val < 0.0:
                    minutos_invalidos += 1
                    continue
            except ValueError:
                minutos_invalidos += 1
                continue

            minutos_validos += 1
            horas_dict[hora_chave].append(pwr_val)

    # Agregação horária sob política conservadora: exatamente 60 minutos válidos por hora
    registros_horarios = []
    horas_completas = 0
    horas_descartadas = 0

    # Ordenar todas as horas possíveis do mês
    for dia in range(1, dias_no_mes + 1):
        for hora in range(24):
            h_str = f"{ano_str}-{mes_str}-{dia:02d} {hora:02d}:00"
            leituras = horas_dict.get(h_str, [])
            if len(leituras) == 60:
                # Hora completa com 60 medições de minuto válidas
                pot_media_hora = sum(leituras) / 60.0
                registros_horarios.append({
                    "data_hora": h_str,
                    "potencia_kw": round(pot_media_hora, 4),
                    "energia_minutos_kwh": sum(leituras) / 60.0,
                    "energia_hora_kwh": pot_media_hora * 1.0,
                })
                horas_completas += 1
            else:
                horas_descartadas += 1

    # Agregação diária para verificar dias completos (24h)
    dias_dict = defaultdict(int)
    for r in registros_horarios:
        dia_chave = r["data_hora"][:10]
        dias_dict[dia_chave] += 1

    dias_completos = sum(1 for d, count in dias_dict.items() if count == 24)
    dias_parciais = sum(1 for d, count in dias_dict.items() if 0 < count < 24)

    cobertura_mensal_pct = (horas_completas / horas_esperadas_mes) * 100.0

    resumo_qualidade = {
        "mes_ano": f"{mes_str}/{ano_str}",
        "dias_no_mes": dias_no_mes,
        "minutos_esperados": minutos_esperados_mes,
        "minutos_encontrados": minutos_encontrados,
        "minutos_validos": minutos_validos,
        "minutos_ausentes_ou_nulos": minutos_ausentes_ou_nulos,
        "minutos_invalidos": minutos_invalidos,
        "minutos_duplicados": minutos_duplicados,
        "horas_esperadas": horas_esperadas_mes,
        "horas_completas": horas_completas,
        "horas_descartadas": horas_descartadas,
        "dias_completos": dias_completos,
        "dias_parciais": dias_parciais,
        "cobertura_mensal_pct": round(cobertura_mensal_pct, 2),
    }

    return registros_horarios, resumo_qualidade


def salvar_csv_derivado(registros: List[Dict[str, Any]], destino_csv: Path) -> None:
    """Salva os registros horários derivados no formato estrito do PowerMonitor."""
    destino_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(destino_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["data_hora", "potencia_kw"])
        for r in registros:
            writer.writerow([r["data_hora"], f"{r['potencia_kw']:.4f}"])
    print(f"-> Arquivo horário derivado exportado com sucesso: {destino_csv} ({len(registros)} medições)")


def main():
    parser = argparse.ArgumentParser(
        description="Preparação do estudo de caso real UCI (Maio/2007) para o PowerMonitor."
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=None,
        help="Caminho opcional do arquivo bruto TXT da UCI (se omitido, busca em /tmp/uci_raw ou baixa automaticamente).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"Caminho do arquivo CSV de saída (default: {DEFAULT_OUT}).",
    )
    parser.add_argument("--ano", type=int, default=2007, help="Ano civil selecionado (default: 2007).")
    parser.add_argument("--mes", type=int, default=5, help="Mês civil selecionado (default: 5 - Maio).")
    args = parser.parse_args()

    txt_file = args.source
    if txt_file is None:
        candidato = LOCAL_RAW_DIR / "household_power_consumption.txt"
        if candidato.exists():
            txt_file = candidato
        else:
            txt_file = baixar_e_extrair_dataset(LOCAL_RAW_DIR)

    registros, resumo = processar_mes_uci(txt_file, ano=args.ano, mes=args.mes)

    print("\n" + "=" * 60)
    print("        RELATÓRIO DE AUDITORIA DE QUALIDADE DOS DADOS (UCI)       ")
    print("=" * 60)
    print(f"Mês e Ano Analisados:        {resumo['mes_ano']}")
    print(f"Dias no Mês Civil:           {resumo['dias_no_mes']}")
    print(f"Minutos Esperados:           {resumo['minutos_esperados']}")
    print(f"Minutos Encontrados:         {resumo['minutos_encontrados']}")
    print(f"Minutos Válidos:             {resumo['minutos_validos']}")
    print(f"Minutos Ausentes ('?'):      {resumo['minutos_ausentes_ou_nulos']}")
    print(f"Minutos Inválidos/Negativos: {resumo['minutos_invalidos']}")
    print(f"Minutos Duplicados:          {resumo['minutos_duplicados']}")
    print(f"Horas Esperadas no Mês:      {resumo['horas_esperadas']}")
    print(f"Horas Completas (60 min OK): {resumo['horas_completas']}")
    print(f"Horas Descartadas (< 60 min):{resumo['horas_descartadas']}")
    print(f"Dias Civis Completos (24h):  {resumo['dias_completos']}")
    print(f"Dias Parciais (< 24h):       {resumo['dias_parciais']}")
    print(f"Cobertura Temporal Mensal:   {resumo['cobertura_mensal_pct']}%")
    print("=" * 60 + "\n")

    salvar_csv_derivado(registros, args.out)


if __name__ == "__main__":
    main()
