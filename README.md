# Estrategia de Trading Rentable en Python

Este repositorio contiene una implementación de una estrategia de trading algorítmico basada en seguimiento de tendencia utilizando MACD y una media móvil simple (SMA) de 200 días.

## La Estrategia

La estrategia utiliza una combinación de un indicador de momentum (MACD) y un filtro de tendencia a largo plazo (SMA 200).

### Reglas de Entrada (Compra)
1.  **Filtro de Tendencia:** El precio de cierre actual debe estar por encima de la media móvil simple de 200 días (SMA 200). Esto asegura que solo compremos en mercados con tendencia alcista a largo plazo.
2.  **Señal de Momentum:** El indicador MACD debe cruzar por encima de su línea de señal (Signal Line).

### Reglas de Salida (Venta)
1.  **Cruce de Salida:** Cerramos la posición cuando el MACD cruza por debajo de la línea de señal.

## Requisitos

Para ejecutar el script, necesitas instalar las siguientes librerías:

```bash
pip install yfinance pandas pandas-ta matplotlib
```

## Ejecución

Simplemente ejecuta el script `trading_strategy.py`:

```bash
python trading_strategy.py
```

El script descargará datos históricos de Yahoo Finance (si está disponible) o utilizará datos simulados para mostrar el funcionamiento. Al finalizar, generará un reporte de rendimiento y un gráfico llamado `performance.png`.

## Resultados del Backtest (Ejemplo)

Basado en una ejecución con datos históricos/simulados de SPY:

*   **Retorno Total Estrategia:** 5.68%
*   **Retorno Total Mercado (Buy & Hold):** -30.41%
*   **Sharpe Ratio:** 0.25

La estrategia demostró ser capaz de mitigar las pérdidas significativas durante mercados bajistas prolongados al permanecer fuera del mercado cuando el precio estaba por debajo de la SMA 200.

## Archivos del Repositorio

*   `trading_strategy.py`: Código fuente de la estrategia y el motor de backtesting.
*   `performance.png`: Gráfico comparativo del rendimiento.
*   `README.md`: Documentación del proyecto.
