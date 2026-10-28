# Running the API on an Oracle Cloud VM (always on)

> **Not in use (28 October 2026):** the owner chose to keep the API on the PC
> with a watchdog that brings it back after restarts
> (`docs/LIVE_DEMO.md`, *Keep it up on its own*). This page is the route for
> when the site must also work while the PC is off.

Until 28 October 2026 the live site's API ran on the owner's PC behind a
temporary tunnel (`docs/LIVE_DEMO.md`). The site went down whenever the PC
slept, restarted or changed network, and the tunnel's address changed each
time. This moves the API to a free **Oracle Cloud Always Free** VM, so
https://mairos.vercel.app works from any laptop at any time and comes back on
its own after the VM restarts.

**What you get:** an Ampere (ARM) VM with up to 4 cores and 24 GB of RAM, free
for as long as the account exists. The API runs in Docker behind
[Caddy](https://caddyserver.com), which gets an HTTPS certificate for
`<public-ip>.sslip.io` by itself (sslip.io turns any IP into a hostname; no
domain to buy). Data lives in `~/mairos-data` on the VM's disk and survives
restarts.

**Cost:** nothing on the Always Free shapes. Oracle asks for a card to verify
the account; stay on "Always Free eligible" resources and it is not charged.

---

## 1. Create the account and the VM (you, in the browser, ~20 minutes)

1. Sign up at <https://www.oracle.com/cloud/free/>. Pick a home region close to
   you; Always Free resources only exist in the home region.
2. Console → **Compute → Instances → Create instance**.
   - **Image:** Canonical Ubuntu 22.04 (or 24.04).
   - **Shape:** Change shape → Ampere → `VM.Standard.A1.Flex`, **2 OCPUs and
     12 GB** memory (inside the free allowance; 4/24 also is).
     If it says *out of host capacity*, try another availability domain, or
     again later — free Ampere capacity comes and goes.
   - **Networking:** keep "Assign a public IPv4 address" on.
   - **SSH keys:** "Generate a key pair for me" and **download the private
     key**. Keep it safe; it is the only way in.
   - **Boot volume:** the default 47 GB is fine.
3. Open ports 80 and 443: on the instance page click the **subnet** → its
   **Security List** → **Add Ingress Rules** twice, Source CIDR `0.0.0.0/0`,
   IP protocol TCP, destination port `80`, then `443`.
4. Note the instance's **public IP address**.

## 2. Log in and get the code onto the VM

From PowerShell on the PC (replace the key path and IP):

```powershell
ssh -i C:\path\to\ssh-key.key ubuntu@<public-ip>
```

The repository is private, so give the VM a read-only **deploy key**:

```bash
ssh-keygen -t ed25519 -N "" -f ~/.ssh/mairos_deploy
cat ~/.ssh/mairos_deploy.pub
```

On GitHub: NeerajMoorthy/MAIROS → **Settings → Deploy keys → Add deploy key**,
paste that line, leave "Allow write access" **off**. Then:

```bash
cat >> ~/.ssh/config <<'EOF'
Host github.com
  IdentityFile ~/.ssh/mairos_deploy
EOF
git clone git@github.com:NeerajMoorthy/MAIROS.git ~/mairos
```

## 3. Settings and data (optional but recommended)

Copy the PC's settings, so the VM uses the same Groq key and models. From
PowerShell **on the PC**, in the `mairos` folder:

```powershell
scp -i C:\path\to\ssh-key.key .env ubuntu@<public-ip>:~/mairos/.env
```

To keep the projects already on the live demo, copy its data folder too:

```powershell
scp -i C:\path\to\ssh-key.key -r ..\mairos-deploy-data ubuntu@<public-ip>:~/mairos-data
```

If you skip the `.env` copy, the setup script asks for the Groq key instead
(typed, never shown). Never paste the key into chat or a file in the repository.

## 4. Run the setup (on the VM)

```bash
cd ~/mairos
bash deploy/oracle/setup.sh
```

It installs Docker, opens 80/443 in the VM's own firewall (Oracle's Ubuntu
images block them even after step 1.3), writes `deploy/oracle/.env` with
`DOMAIN=<public-ip>.sslip.io`, builds the API image (10–20 minutes the first
time) and starts the API and Caddy. It finishes by printing the address and
the two commands for the next step. Running it again is safe.

Check from any browser: `https://<public-ip>.sslip.io/api/health` should
answer `{"status":"ok", ...}`.

## 5. Point the website at the VM (on the PC, once)

In `mairos\apps\web` (logged in to Vercel as `moorthyneeraj2008-5702`):

```powershell
npx vercel env add MAIROS_API_URL production --value https://<public-ip>.sslip.io --force --yes
npx vercel env add MAIROS_API_URL preview --value https://<public-ip>.sslip.io --force --yes
npx vercel deploy --prod --yes
```

Then stop the PC's demo for good:

```powershell
cd ..\..
.venv\Scripts\python scripts\publish_demo.py --stop
```

**Do not run Start MAIROS (`start_demo.bat`) any more**, or
`publish_demo.py` without `--stop`: it would point the site back at a tunnel
on the PC. Delete the desktop shortcut to be safe.

## Day to day

- **Nothing to do** when the PC restarts: the site no longer depends on it.
- **VM restarts** (Oracle maintenance, or you reboot it): Docker starts both
  containers again by itself; the address does not change.
- **Ship new backend code:** on the VM, `bash ~/mairos/deploy/oracle/update.sh`
  (pulls `main`, rebuilds, restarts). Frontend changes still go out with
  `npx vercel deploy --prod` from `apps/web`.
- **Logs:** `cd ~/mairos/deploy/oracle && sudo docker compose logs --tail 100 api`.
- **Idle reclamation:** Oracle may reclaim an Always Free VM that stays almost
  completely idle for 7 days. A demo that people use is not idle; if in doubt,
  upgrading the account to Pay As You Go keeps the free shapes free and stops
  reclamation.
