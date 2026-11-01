# SA Market Monitor (free, EOD)

Roz shaam ko NSE bhavcopy se MR20, U4, D4, W20 nikalta hai, regime/setup/note lagata hai, aur website par dikhata hai. Sab free: GitHub Actions (data) + GitHub Pages (site).

## Files

- `index.html` : website (data.json padhti hai)
- `data.json` : tumhari sheet ka poora history (2016 se 9 Oct 2026), roz naya din judta hai
- `update.py` : bhavcopy download + calculation
- `sa_logic.py` : regime / setup / note ke rules (Word prompt wale)
- `build_data.py` : sheet se data.json dobara banane ke liye (zaroorat nahi padegi)
- `.github/workflows/update.yml` : roz 7 PM IST par update.py chalata hai

## Setup (10 minute)

1. GitHub par naya **public** repo banao (e.g. `sa-monitor`) aur ye saari files upload karo (`.github` folder samet).
2. Repo me **Settings > Pages > Build and deployment**: Source = "Deploy from a branch", Branch = `main`, folder = `/ (root)`. Save.
3. **Actions** tab me "Daily EOD update" kholo aur **Run workflow** dabao. Pehli baar ye 12 Oct se aaj tak ka gap bharega aur EMA ke liye ~150 din ki history download karega (kuch minute lagenge).
4. Site `https://<tumhara-username>.github.io/sa-monitor/` par khulegi. Uske baad roz apne aap update hogi.

## Pehle din ye zaroor check karo

- **Chartink se milao.** Gap bharne ke baad 12 Oct se 30 Oct ke MR20/U4/D4/W20 apne Chartink ke numbers se compare karo. Agar thoda fark ho to `update.py` ke upar `TURNOVER_MIN`, `U4_PCT` aur U4/D4 ka volume condition tumhare scan jaisa kar do.
- Bhavcopy ka URL/columns NSE ne pehle badle hain. Agar Actions me "unexpected columns" ya "No new trading days" aaye to log dekho aur URL wali `URLS` list update karo.
- Raw bhavcopy unadjusted hota hai. Script split/bonus NSE ke `PrvsClsgPric` column se adjust karti hai. Ye assumption hai ki NSE ex-date par ye column adjust karta hai; kisi split wale din ek baar manually check kar lena.
- Regime logic tumhari sheet ke 2661 me se 2637 din se match karta hai. Chop ka rule sheet se calibrate hua hai: pichle 5 MR20 moves me 3+ baar direction badli.
- Agar repo kai hafte inactive rahe to GitHub scheduled workflow band kar sakta hai. Actions tab se dobara enable kar do.
