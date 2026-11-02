# Yahoo Fantasy NBA weekly report

Every Monday, GitHub pulls your league from the Yahoo Fantasy API and publishes a dashboard page. You just open the link.

The page shows:
- your standing
- last week's result, with your rank in each category
- your season strengths and weaknesses
- your category ranks week by week
- your record if you'd played every team (this takes schedule luck out of the picture)
- a preview of next week's opponent, with your win chance in each category

No libraries to install. It's plain Python 3.

## One-time setup (about 10 min)

**1. Create a Yahoo app.** Go to https://developer.yahoo.com/apps/create/
- Application name: anything
- Redirect URI: `https://localhost:8080`
- API Permissions: tick **Fantasy Sports → Read**
- Create the app, then copy the **Client ID** and **Client Secret**.

**2. Get your refresh token.** You only do this once. On your own computer, in this folder, run:
```
python get_token.py
```
Paste the ID and secret. A Yahoo page opens. Click Agree. The browser then goes to a `localhost` page that won't load. That's expected. Copy that URL from the address bar and paste it into the terminal. The script prints a refresh token.

**3. Create a GitHub repo and push this folder.** Make the repo **public**: GitHub Pages on a private repo needs a paid plan. Your keys stay private either way, because they're stored as secrets. Only the dashboard page is public.

**4. Add secrets.** In the repo, go to Settings → Secrets and variables → Actions → New repository secret, and add:
- `YAHOO_CLIENT_ID`
- `YAHOO_CLIENT_SECRET`
- `YAHOO_REFRESH_TOKEN`
- `YAHOO_LEAGUE_ID`: optional. It's the number in your league URL (`basketball.fantasysports.yahoo.com/nba/12345`). You only need it if you're in more than one NBA league.

**5. Turn on Pages.** Go to Settings → Pages → Source and choose **GitHub Actions**.

**6. First run.** Go to Actions → "Weekly fantasy report" → Run workflow. When it finishes, the page is at `https://<your-username>.github.io/<repo-name>/`. Bookmark it on your phone.

After that, it updates on its own every Monday at about noon Israel time.

## Preview with fake data
```
python demo_data.py && python report.py data/demo.json site/demo.html
```

## Notes
- **Category vs. points leagues:** head-to-head category leagues get the full analysis. Points leagues work too: "vs everyone" and next-week odds use weekly points.
- **Win chances are rough:** they're a simple estimate from season and last-3-week averages. They don't account for injuries or how many games each team plays that week.
- **Early season:** with only 1–2 weeks played, the trends are noisy.
