# Hosting via Cloudflare Tunnel (single user, business hours)

Run the full app on your machine and let authorized people reach it through a
browser — no open router ports, no client install on their end, just a URL and
an email login. The app enforces **one user at a time** and **business hours**.

```
Browser ──HTTPS──► Cloudflare (login) ──tunnel──► your machine: localhost:8501
```

## Prerequisites
- A **Cloudflare account** (free) and a **domain added to Cloudflare** (needed
  for a named tunnel + Access). Any cheap domain works.
- The app running locally and reachable at `http://localhost:8501`.

## 1. Install cloudflared
Windows (PowerShell):
```powershell
winget install --id Cloudflare.cloudflared
```
(or download the `.msi` from Cloudflare's site).

## 2. Create the tunnel
```powershell
cloudflared tunnel login            # opens browser; pick your domain
cloudflared tunnel create maint-app # creates a tunnel + credentials .json
```
Note the tunnel UUID and the credentials file path it prints.

## 3. Configure it
Create `C:\Users\<you>\.cloudflared\config.yml`:
```yaml
tunnel: <TUNNEL-UUID>
credentials-file: C:\Users\<you>\.cloudflared\<TUNNEL-UUID>.json
ingress:
  - hostname: maint.yourdomain.com
    service: http://localhost:8501
  - service: http_status:404
```
Route DNS to it:
```powershell
cloudflared tunnel route dns maint-app maint.yourdomain.com
```

## 4. Lock it down with Cloudflare Access
In the Cloudflare **Zero Trust** dashboard → **Access → Applications**:
1. **Add an application** → Self-hosted → domain `maint.yourdomain.com`.
2. Add a **policy**: Action **Allow**, Include → **Emails** → list the people
   who may use it. They'll get a one-time PIN by email to log in.
3. (Optional) Set a short **session duration** so logins expire.

Now only those emails can reach the app, and everyone else gets a login wall.

## 5. Run it
Start the app with the gates enabled (PowerShell, in the repo, venv active):
```powershell
$env:SINGLE_USER  = "1"
$env:BUSINESS_HOURS = "1"
$env:BIZ_START = "8"; $env:BIZ_END = "17"; $env:BIZ_DAYS = "0-4"   # Mon–Fri 8–5
$env:QWEN_MODEL = "qwen2.5:3b"          # or your model; omit DISABLE_LLM for full
streamlit run app.py --server.address=localhost
```
In a second window, start the tunnel (or install it as a service so it survives
reboots):
```powershell
cloudflared tunnel run maint-app
# or: cloudflared service install   (runs the tunnel in the background)
```

That's it. Authorized users open `https://maint.yourdomain.com`, log in with
their email PIN, and use the tool. Outside business hours they see a "closed"
message; if someone's already in, the next person sees "in use — try again."

## Notes
- **Times use your machine's local clock** — set the server's timezone correctly.
- **Single-user** releases automatically ~2 minutes after a user goes idle or
  disconnects (`SESSION_TIMEOUT`, default 120s).
- The app stays bound to **localhost**; cloudflared is the only thing that
  reaches it, so nothing is exposed on your LAN or router.
- Your machine must be **on and online** during business hours. A Proxmox VM
  that stays up is the natural home; pair with `scripts/backup.sh`.
- To take it offline, stop the tunnel (`cloudflared`), the app keeps running
  locally only.
