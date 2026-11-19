"""
Executa o pipeline completo da solução de BI da Mercatto:

    1. Geração da base sintética   (src/gerar_base.py)  -> data/raw/*.csv
    2. ETL                         (src/etl.py)         -> data/processed/bi.db + CSV
    3. Validação de qualidade      (src/validacao.py)   -> reports/relatorio_qualidade.md
    4. Análise e modelos           (src/analise.py)     -> tabelas an_* + reports/resultados_analise.json

Depois, abra o dashboard com:
    streamlit run dashboard/app.py

Uso:
    python run_all.py                 # semente padrão 42 (resultados idênticos aos documentados)
    python run_all.py --seed 7        # outra base, mesmo processo
"""
import argparse
import sys
import time

from src import analise, etl, gerar_base, validacao


def etapa(nome, func, *args):
    t0 = time.perf_counter()
    print(f"\n=== {nome} ===")
    resultado = func(*args)
    print(f"--- concluído em {time.perf_counter() - t0:.1f}s")
    return resultado


def main():
    ap = argparse.ArgumentParser(description="Pipeline completo da solução de BI Mercatto")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--clientes", type=int, default=8000)
    args = ap.parse_args()

    r = etapa("1/4 Geração da base sintética", gerar_base.main, args.seed, args.clientes)
    print("Linhas geradas:", r["linhas_geradas_sem_problemas"])
    log = etapa("2/4 ETL", etl.main)
    print("Linhas carregadas:", log["linhas_carregadas"])
    ok = etapa("3/4 Validação de qualidade", validacao.main)
    if not ok:
        print("\nValidação falhou — veja reports/relatorio_qualidade.md. Pipeline interrompido.")
        sys.exit(1)
    res = etapa("4/4 Análise (KPIs, RFM + K-means, previsão, anomalias)", analise.main)
    print(f"K-means: k={res['kmeans']['k_escolhido']} | silhouette={res['kmeans']['silhouette']:.3f}")
    for m in res["previsao"]["metricas_backtest"]:
        marca = "  <- escolhido" if m["escolhido"] else ""
        print(f"Previsão — {m['modelo']}: MAPE médio={m['MAPE']:.1%}{marca}")

    print("\nPipeline concluído. Para abrir o dashboard:\n    streamlit run dashboard/app.py")


if __name__ == "__main__":
    main()
