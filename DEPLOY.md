# Deploy → Verify → Submit

Three things stood between the code and the finish line. Two are now one-command;
the last needs your login. Pick **one** deploy path.

## 0. Push to GitHub first (needed by Render/Railway)
```bash
cd vera-bot
git init && git add . && git commit -m "Vera message engine"
git branch -M main
git remote add origin https://github.com/singhsiddhant465/vera-bot.git   # create this empty repo first
git push -u origin main
```

## 1. Deploy (fastest paths)

### Option A — Render (free, easiest, stays live)
1. render.com → **New → Blueprint** → pick the `vera-bot` repo (it reads `render.yaml`).
2. When prompted, set **`VERA_CONTACT_EMAIL`** = your DTU college email.
3. Deploy. Your public URL is `https://vera-bot-XXXX.onrender.com`.
   - Note: Render free instances sleep after inactivity. The judge polls `/v1/healthz`
     every 60s, which keeps it warm — but hit the URL once right before the test window
     opens so the first request isn't a cold start.

### Option B — Railway (no Docker; uses `Procfile`)
1. railway.app → **New Project → Deploy from GitHub** → pick the repo.
2. Variables tab → add `VERA_CONTACT_EMAIL`, `VERA_TEAM_NAME`, `VERA_TEAM_MEMBERS`.
3. Railway gives you a `*.up.railway.app` URL. Enable "Public Networking".

### Option C — Fly.io (uses `fly.toml`, kept always-on)
```bash
fly launch --no-deploy        # accept the existing fly.toml
fly secrets set VERA_CONTACT_EMAIL="you@college.ac.in"
fly deploy
fly status                     # shows the https URL
```

### Option D — Quick temporary URL (ngrok, for a fast judge test only)
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080
ngrok http 8080               # gives https://xxxx.ngrok-free.app  (keep the terminal open)
```

## 2. Verify the live URL before submitting
```bash
BASE="https://YOUR-PUBLIC-URL"
curl -s $BASE/v1/healthz     # {"status":"ok",...}
curl -s $BASE/v1/metadata    # confirm team_name + your college contact_email

# full scored run against the deployed bot (edit BOT_URL + LLM key in judge_simulator.py):
cd /path/to/magicpin-ai-challenge
#   set BOT_URL = "https://YOUR-PUBLIC-URL"  and your LLM_PROVIDER + LLM_API_KEY
python judge_simulator.py
```
Health check must pass for the whole window — **3 consecutive `/v1/healthz` failures = disqualified.**

## 3. Submit (this part is yours — needs your portal login + college email)
Submit the **public URL** via the challenge portal, signed in with your **DTU college email ID**
(the HR email required this). Paste-ready fields:

- **Team name:** Siddhant Singh
- **Members:** Siddhant Singh
- **Bot URL:** `https://YOUR-PUBLIC-URL`
- **Repo:** `https://github.com/singhsiddhant465/vera-bot`
- **Approach (one line):** Deterministic rules composer — dispatch by `trigger.kind`, ground every
  fact in pushed context, single-CTA output; optional temp-0 LLM rephraser (off by default).

## Final pre-flight checklist
- [ ] `VERA_CONTACT_EMAIL` set to your college email (shows in `/v1/metadata`)
- [ ] Public URL responds on `/v1/healthz` and `/v1/metadata`
- [ ] `judge_simulator.py` ran green against the **deployed** URL
- [ ] Bot will stay live for the full test window (no free-tier sleep surprise)
- [ ] URL submitted via portal **from the college email ID**
