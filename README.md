# 🏦 Hedge Fund Terminal Pro – Spot + CFD Simulator

A complete educational paper-trading terminal that simulates how a real multi-strategy hedge fund operates.

## Features

### Trading
- **Spot / Physical** positions (stocks & crypto) – full capital outlay
- **CFD** positions – leveraged, long & short, margin-based
- Real market data via Yahoo Finance (`yfinance`)
- Market orders with simulated commission

### Risk Management
- Different overnight financing rates for **Long CFDs** vs **Short CFDs**
- Automated daily financing deductions
- Detailed financing history log
- Automatic position reduction on margin call
- Position size calculator (risk % of equity)
- Max position size limits

### Analytics & Tools
- Live equity curve with starting capital reference
- Portfolio allocation pie chart
- Full trade journal
- Performance summary
- Watchlist support
- Dark / Light theme toggle

### Education
- Built-in lessons on hedge fund structure
- Long vs Short CFD financing explained
- Margin call mechanics
- Professional risk rules

## Quick Start

```bash
# 1. Install dependencies
pip install streamlit yfinance pandas plotly numpy

# 2. Run the app
streamlit run app.py
```

The app will open in your browser at `http://localhost:8501`.

## How to Use

1. **Place trades** from the sidebar  
   - Choose Spot or CFD  
   - For CFD select leverage (1x–20x)

2. **Monitor financing**  
   - Long CFDs cost money every day  
   - Short CFDs can earn a small credit  
   - Check the Financing History tab

3. **Risk tools**  
   - Use the Position Sizer before every trade  
   - Watch the Margin Used metric  
   - Automatic reduction happens if free cash becomes too low

4. **Export**  
   - Trade journal  
   - Financing log  
   - Performance summary  
   (all available as CSV in the Settings tab)

## Default Settings

| Setting                    | Default     | Description                          |
|---------------------------|-------------|--------------------------------------|
| Starting Capital          | $1,000,000  | Virtual fund AUM                     |
| Long CFD Rate             | 8.5%        | Annualized – you pay                 |
| Short CFD Rate            | -1.5%       | Annualized – you receive credit      |
| Max Position Size         | 30%         | Of total equity                      |
| Default Risk per Trade    | 1%          | Of equity                            |
| Margin Call Threshold     | 15%         | Free cash vs margin used             |

You can change all of these in the **Settings & Export** tab.

## File Structure

```
.
├── app.py                  # Main application
├── README.md               # This file
└── hf_terminal_final.json  # Auto-created state file (persistent)
```

## Important Notes

- This is an **educational paper-trading simulator** only.
- Not financial advice.
- Market data comes from Yahoo Finance and may be delayed.
- Financing is calculated and applied every time you open the app.
- State is saved locally in `hf_terminal_final.json`.

## Future Ideas

- Limit & Stop orders that trigger automatically
- Simple strategy backtester
- Portfolio correlation matrix
- Multi-user / login support
- More asset classes (options, futures)

---

Built for learning how real hedge funds combine physical holdings, leveraged CFDs, financing costs, and strict risk controls.
```