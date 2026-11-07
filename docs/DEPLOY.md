# GNR LMS: step-by-step deploy guide

This takes you from "no server" to "instructors are using the LMS on its own web address". Plan for about 2 hours the
first time. Every command is meant to be copied and pasted.

**Before you start, decide one thing: the web address.** This guide writes it as `lms.YOUR-DOMAIN.com`. Everywhere
you see that, type your real address instead (for example `lms.gnrrobotics.com` if you own `gnrrobotics.com`). You
need to be able to log in to the place where that domain was bought (GoDaddy, Hostinger, Namecheap, Cloudflare, etc.).

**Rule for keys and passwords:** Bunny keys, database passwords and the secret key go **only** into the `.env` file on
the server (step 6). Don't paste them into chat, email, WhatsApp, GitHub or a document.

What you will pay for: the server (about $12 a month) and Bunny (already set up). Everything else in this guide is free.

---

## Step 1. Create the server (about 10 minutes)

**Recommended: DigitalOcean, Bangalore, 2 GB RAM, $12 a month.** Bangalore is close to your students, so pages load
quickly. 2 GB is enough while only instructors use it. When students join you can resize to a bigger plan in two
clicks (step 15).

1. Go to <https://www.digitalocean.com> and sign up. Add a card (they may charge and refund a small amount to check it).
2. Top right: **Create → Droplets**.
3. **Choose Region:** **Bangalore** (BLR1).
4. **Choose an image:** **Ubuntu**, version **24.04 (LTS) x64**.
5. **Choose Size:** **Basic** → **Regular** (SSD) → the **$12/mo** one (**2 GB / 1 CPU / 50 GB disk / 2 TB transfer**).
6. Leave **additional storage** and **automatic backups** off (we set up free backups in step 13).
7. **Choose Authentication Method:** pick **SSH Key**, then **New SSH Key**. Keep this browser tab open and do step 2 to
   get the key, then come back.
8. **Hostname:** type `gnr-lms`.
9. Click **Create Droplet**. After about a minute it shows an **IP address** like `139.59.12.34`. Write it down. This
   guide calls it `SERVER-IP`.

*Cheaper alternative:* Hetzner Cloud (<https://www.hetzner.com/cloud>) has servers with more memory for less money,
but its nearest location is Singapore (a little slower from India) and new accounts sometimes need ID verification.
If you pick Hetzner: location **Singapore**, image **Ubuntu 24.04**, the smallest **shared vCPU** plan with **4 GB**
RAM, add your SSH key the same way. Everything after this step is the same.

## Step 2. Make an SSH key on your Windows PC (5 minutes)

An SSH key is how your PC proves it is you when it logs in to the server. No password to remember or steal.

1. Press the **Windows key**, type `PowerShell`, open **Windows PowerShell**.
2. Paste this and press **Enter**:
   ```powershell
   ssh-keygen -t ed25519 -C "ramkiran-pc"
   ```
   Press **Enter** three times (accept the default place, and no passphrase, or type one if you prefer).
3. Show the public key:
   ```powershell
   type $env:USERPROFILE\.ssh\id_ed25519.pub
   ```
   It prints one line starting with `ssh-ed25519`. Select the whole line, right-click to copy.
4. Back in the DigitalOcean tab, paste it into **SSH key content**, name it `ramkiran-pc`, click **Add SSH Key**, then
   finish step 1 (Create Droplet).

The `.pub` file is safe to share. The other file (`id_ed25519`, no `.pub`) is your private key: never send it anywhere.

## Step 3. Log in to the server (2 minutes)

In PowerShell:
```powershell
ssh root@SERVER-IP
```
The first time it asks `Are you sure you want to continue connecting?`. Type `yes` and press Enter. You are now
typing on the server; the prompt changes to something like `root@gnr-lms:~#`.

To paste into PowerShell, right-click. To leave the server, type `exit`.

## Step 4. Prepare the server (10 minutes)

Paste these blocks one at a time while logged in as `root`.

**4a. Updates, firewall and swap** (swap is spare memory on disk, which stops the 2 GB server running out of memory
while it builds):
```bash
apt update && apt -y upgrade
apt -y install ufw rclone git
ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw allow 443/udp && ufw --force enable
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
timedatectl set-timezone Asia/Kolkata
```
If it shows a pink screen asking about restarting services or a config file, press **Enter** to accept the default.

**4b. Install Docker:**
```bash
curl -fsSL https://get.docker.com | sh
```

**4c. Make a normal user called `gnr`** (safer than doing everything as root) and let it use your SSH key and Docker:
```bash
adduser --disabled-password --gecos "" gnr
usermod -aG sudo,docker gnr
rsync --archive --chown=gnr:gnr ~/.ssh /home/gnr
echo 'gnr ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/gnr
exit
```

From now on, log in as `gnr`:
```powershell
ssh gnr@SERVER-IP
```
Check Docker works: `docker run --rm hello-world` should print "Hello from Docker!".

## Step 5. Point your web address at the server (5 minutes, then wait)

Do this now, because it can take from a few minutes to an hour to start working.

1. Log in where your domain is managed and open its **DNS** settings (sometimes called "DNS Management", "Zone editor"
   or "Advanced DNS").
2. **Add a record:**
   - **Type:** `A`
   - **Name / Host:** `lms` (only the first part, not the whole address)
   - **Value / Points to:** `SERVER-IP`
   - **TTL:** 5 minutes / 300 (or "Automatic")
3. Save.
4. **If your DNS is on Cloudflare:** click the orange cloud next to the record so it turns **grey ("DNS only")**.
   The server makes its own HTTPS certificate and that needs a direct connection.

Check from PowerShell on your PC (not on the server):
```powershell
nslookup lms.YOUR-DOMAIN.com
```
When the answer shows `SERVER-IP`, it's ready. Carry on with step 6 while you wait.

## Step 6. Download the LMS and fill in its settings (15 minutes)

On the server, as `gnr`:
```bash
cd ~
git clone https://github.com/ramkirangaruda/gnr-lms.git
cd gnr-lms
cp .env.example .env
chmod 600 .env
```

Make two random passwords. Run this; it prints two long lines:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50)); print(secrets.token_hex(24))"
```
The first line is your **secret key**, the second your **database password**. Keep the window open, you paste them in
a moment. (They don't need to be written down anywhere else; they live in `.env`.)

Open the settings file:
```bash
nano .env
```
`nano` is a simple text editor. Move with the arrow keys; right-click pastes. Change these lines (delete the old value
after `=` and type or paste the new one, no spaces around `=`):

| Line | What to put |
|---|---|
| `DJANGO_SECRET_KEY=` | the first random line |
| `DJANGO_DEBUG=0` | leave as `0` |
| `LMS_DOMAIN=` | `lms.YOUR-DOMAIN.com` |
| `DJANGO_ALLOWED_HOSTS=` | `lms.YOUR-DOMAIN.com` |
| `DJANGO_CSRF_TRUSTED_ORIGINS=` | `https://lms.YOUR-DOMAIN.com` |
| `SECURE_COOKIES=1` | leave as `1` |
| `WEB_CONCURRENCY=` | `3` on the 1-CPU $12 server (`5` on 2 CPUs, `9` on 4 CPUs) |
| `POSTGRES_DB=gnr_lms`, `POSTGRES_USER=gnr` | leave as they are (the backup check script expects them) |
| `POSTGRES_PASSWORD=` | the second random line |

**Bunny Stream** (lesson videos). Remove the `# ` at the start of these lines and fill them in. Get the values from the
Bunny dashboard: <https://dash.bunny.net> → **Stream** → **Video Lectures** library:

| Line | Where to find it in Bunny |
|---|---|
| `BUNNY_STREAM_LIBRARY_ID=` | library → **API** tab → **Video Library ID** (a number) |
| `BUNNY_STREAM_API_KEY=` | library → **API** tab → **API Key**. Use this library's key, **not** the account API key from Account settings. |
| `BUNNY_STREAM_TOKEN_KEY=` | library → **Security** tab → **Embed View Token Authentication** → **Token authentication key**. (Step 10 explains switching it on.) |
| `BUNNY_STREAM_EMBED_TTL=14400` | leave as is (a player link works for 4 hours) |

To copy from Bunny: click the copy icon next to the value, then right-click in the PowerShell window to paste.

**Leave these for later** (keep the `#` in front for now; steps 11 to 13 come back to them):
`EMAIL_*`, `DEFAULT_FROM_EMAIL`, `BACKUP_REMOTE`, `SENTRY_DSN`, `DJANGO_ADMINS`.

Save and close nano: press **Ctrl+O**, **Enter**, then **Ctrl+X**.

Check nothing still says `change-me`:
```bash
grep -n "change-me" .env || echo "OK, no placeholders left"
```

## Step 7. Start it (10 minutes)

Only once `nslookup` from step 5 shows your server's IP:
```bash
cd ~/gnr-lms
docker compose up -d --build
```
The first build takes 3 to 8 minutes. Then check all four parts are running:
```bash
docker compose ps
```
You want `db`, `redis`, `web` and `caddy` all `Up`, and `web` saying `(healthy)` after about a minute.

Watch the HTTPS certificate being made:
```bash
docker compose logs caddy | grep -i -E "certificate obtained|error"
```
"certificate obtained successfully" means done. Now open **https://lms.YOUR-DOMAIN.com/healthz** in your browser. It
should show `{"status": "ok"}`. Then open **https://lms.YOUR-DOMAIN.com** and you should see the login page with a
padlock in the address bar.

If something is wrong, see "When something doesn't work" at the end.

## Step 8. Create your owner account (2 minutes)

Pick a username (for example `ramkiran`), then:
```bash
docker compose exec web python manage.py setup_gnr --owner ramkiran
docker compose exec web python manage.py changepassword ramkiran
```
The second command asks for the password twice (nothing shows while you type; that's normal). Use a strong password:
at least 12 characters, not used anywhere else.

Log in at https://lms.YOUR-DOMAIN.com with it.

## Step 9. Demo logins: keep them off the live server

The demo accounts (`instructor1 / instructor123`, `school_demo / school123`, `demo260001 / student123`) exist only on
your PC copy. Their passwords are public, so:

- **Never run `setup_gnr --demo` on the server.**
- Check none slipped in:
  ```bash
  docker compose exec web python manage.py shell -c "from accounts.models import User; print(list(User.objects.filter(username__in=['instructor1','school_demo']).values_list('username', flat=True)) or 'no demo logins, good')"
  ```
  If it lists any, delete them on **Logins** in the LMS (or in `/admin/` → Users).
- If your PC copy is ever reachable from the internet (it shouldn't be), change those passwords there too.

**Add your instructors:** in the LMS go to **Logins → Add login**, role **Instructor**. Give each one a temporary
password; they're asked to pick their own on first login. Send each person their password directly, not in a group.

## Step 10. Videos on Bunny: lock them down, then attach them to lessons

**10a. Turn on Bunny's security** (dash.bunny.net → **Stream** → **Video Lectures** → **Security**):

1. **Embed View Token Authentication: ON.** Now videos only play through the signed link the LMS creates for
   logged-in, enrolled users. (Bunny's own "share" or preview links will stop working outside the dashboard. That's
   expected.)
2. **Allowed Referrers:** add `lms.YOUR-DOMAIN.com`. Videos then refuse to play when embedded on any other site.
3. **Block direct URL file access: ON.** Stops people downloading the raw video file by URL.
4. Click **Save**.

If you changed anything in `.env` after step 7, restart: `docker compose up -d`.

**10b. Attach videos you already uploaded in the Bunny dashboard.** First the courses and lessons have to exist in the
LMS (**Courses → New course**, then **Add lesson**). Then for each lesson:

1. In Bunny: **Stream → Video Lectures →** open the collection (for example **Book 1 - English**) → click the video.
   Copy its **Video ID** (it looks like `1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d`). Copying the video's embed link also
   works.
2. In the LMS: open the lesson → **Edit lesson** → paste it into **"Or use a video already in Bunny (video ID)"** →
   **Save**.
3. Open the lesson as a student would (or log in with a test student) and press play.

*That paste box is new.* It's in a pull request; it appears after the PR is merged and you update the server (see
"Updating the LMS" at the end). Until then, an instructor can use **Upload lesson video** on the lesson form, which
sends the file straight to Bunny.

**10c. Uploading new videos from the LMS:** **Edit lesson → Upload lesson video**, choose the file, wait for 100%,
click **Save**. Bunny needs a few minutes to prepare it before it plays. Videos uploaded this way go to the top of the
library, not into a collection. That's fine; the LMS finds them by ID.

**Careful, this deletes videos in Bunny:** replacing a lesson's video, ticking "Remove the Bunny Stream video", or
deleting a lesson or a whole course **also deletes that video from your Bunny library**. Keep the Google Drive
originals as your backup.

## Step 11. Free uptime monitor (5 minutes)

So you get an email if the site goes down at night.

1. Sign up free at <https://uptimerobot.com>.
2. **New monitor** → type **HTTP(s)** → **Friendly name** `GNR LMS` → **URL**
   `https://lms.YOUR-DOMAIN.com/healthz` → interval **5 minutes** → alert contact: your email (add your phone in the app
   if you like).
3. **Create monitor.** It should go green within a few minutes.

## Step 12. Error alerts (optional, 10 minutes, free)

Tells you about errors users hit, with the details needed to fix them.

- **Sentry:** sign up at <https://sentry.io> (free Developer plan) → create a project, platform **Django** → copy the
  **DSN** (a URL starting `https://`). On the server: `nano .env`, set `SENTRY_DSN=` to it (remove the `#`), save,
  then `docker compose up -d`.
- **Email instead:** set `DJANGO_ADMINS=Ramkiran <your@email.com>`. This only works once email (below) is set up.

**Email for "Forgot password?" (optional).** Until you set it up, staff reset passwords from **Logins** (the key icon),
which works for students without email anyway. When you want it: free Brevo account, verify your domain there, copy the
SMTP login and key into the `EMAIL_*` lines in `.env` (the README section "Email for password resets" has the exact
values), `docker compose up -d`, then test:
`docker compose exec web python manage.py sendtestemail your@email.com`

## Step 13. Nightly backups that leave the server (15 minutes)

A backup stored only on the server is lost if the server is lost. We copy it every night to **Backblaze B2** (10 GB
free, more than enough because videos live on Bunny).

**13a. Make the storage bucket:**
1. Sign up at <https://www.backblaze.com/sign-up/cloud-storage>.
2. **B2 Cloud Storage → Buckets → Create a Bucket.** Name: something unique like `gnr-lms-backups-2026`. Files:
   **Private**. Create.
3. **Application Keys → Add a New Application Key.** Name `gnr-lms-server`, allow access to **only that bucket**,
   **Read and Write**. Create. It shows a **keyID** and an **applicationKey** once. Keep the page open.

**13b. Connect the server to it** (on the server, as `gnr`):
```bash
rclone config
```
Answer the questions:
- `n` (new remote) → name: `b2`
- Storage: type `b2` and press Enter (or the number shown next to "Backblaze B2")
- `account`: paste the **keyID**
- `key`: paste the **applicationKey**
- `hard_delete`: press Enter (default)
- Edit advanced config: `n` → Keep this remote: `y` → Quit: `q`

Test: `rclone lsd b2:gnr-lms-backups-2026` (shows nothing, but no error).

**13c. Tell the LMS:** `nano .env`, set `BACKUP_REMOTE=b2:gnr-lms-backups-2026` (remove the `#`), save.

**13d. Run one backup by hand and check the restore works:**
```bash
cd ~/gnr-lms
sh deploy/backup.sh
sh tests/ops/backup_restore_check.sh
```
The first should end with "copied off-server" and "backup ok". The second prints `live:` and `restored:` lines; the
numbers should match.

**13e. Run it every night at 2 AM:**
```bash
crontab -e
```
If it asks which editor, pick `1` (nano). Go to the bottom and add this line:
```
0 2 * * * cd /home/gnr/gnr-lms && sh deploy/backup.sh >> backups/backup.log 2>&1
```
Save (Ctrl+O, Enter, Ctrl+X). Tomorrow, check with `tail backups/backup.log`.

## Step 14. Final check (run on the server)

Paste this whole block. Every line should say OK.
```bash
cd ~/gnr-lms
D=$(grep -E '^LMS_DOMAIN=' .env | cut -d= -f2)
docker compose ps --format '{{.Service}} {{.Status}}' | grep -q 'web.*healthy' && echo "OK web healthy" || echo "PROBLEM web not healthy"
[ "$(docker compose ps -q | wc -l)" = 4 ] && echo "OK 4 containers up" || echo "PROBLEM not all 4 containers up"
curl -fsS "https://$D/healthz" | grep -q ok && echo "OK https://$D/healthz" || echo "PROBLEM healthz"
curl -sI "http://$D" | grep -qi "location: https" && echo "OK http redirects to https" || echo "PROBLEM no https redirect"
grep -q '^DJANGO_DEBUG=0' .env && echo "OK debug off" || echo "PROBLEM debug not 0"
grep -q 'change-me' .env && echo "PROBLEM placeholder left in .env" || echo "OK no placeholders"
[ "$(stat -c %a .env)" = 600 ] && echo "OK .env private" || echo "PROBLEM run: chmod 600 .env"
grep -q '^BUNNY_STREAM_TOKEN_KEY=.' .env && echo "OK Bunny token key set" || echo "PROBLEM Bunny token key missing"
grep -q '^BACKUP_REMOTE=.' .env && echo "OK backup remote set" || echo "PROBLEM BACKUP_REMOTE missing"
crontab -l 2>/dev/null | grep -q backup.sh && echo "OK nightly backup scheduled" || echo "PROBLEM no backup in crontab"
docker compose exec -T web python manage.py shell -c "from accounts.models import User; print('PROBLEM demo login exists' if User.objects.filter(username__in=['instructor1','school_demo']).exists() else 'OK no demo logins')"
sudo ufw status | grep -q "443" && echo "OK firewall allows https" || echo "PROBLEM firewall"
free -h | grep -i swap
```

Then by hand, in your browser:
- [ ] Log in as the owner; padlock shows in the address bar.
- [ ] Create one test instructor and one test student; log in as each in a private/incognito window.
- [ ] One lesson with a Bunny video plays for an enrolled student; a not-enrolled student can't open it.
- [ ] Copy the video's player address into another browser where you're not logged in: it should refuse to play.
- [ ] UptimeRobot shows green.
- [ ] Try a phone on mobile data as well as office Wi-Fi.

## Step 15. Before students arrive

- **Resize the server** when students start: DigitalOcean → your droplet → **Resize** → **CPU and RAM only** (so you
  can go back down later) → **2 vCPU / 4 GB ($24)**. Power off first when it asks; it takes about a minute. Then set
  `WEB_CONCURRENCY=5` in `.env` and run `docker compose up -d`. For whole schools logging in during the same minute,
  4 vCPU / 8 GB with `WEB_CONCURRENCY=9`. (From the launch test: a login costs about 0.2 s of CPU, so 500 students
  logging in at the same moment wait 25 to 45 s on 2 CPUs. Let classes log in a few minutes apart.)
- Bulk-create student logins from **Logins → Auto-generate** and print the slips.

---

## Updating the LMS later

When there's new code on GitHub (for example after merging a pull request):
```bash
cd ~/gnr-lms
sh deploy/backup.sh
git pull
docker compose up -d --build
```
Database changes apply by themselves on start. Check https://lms.YOUR-DOMAIN.com/healthz afterwards.

## When something doesn't work

| What you see | What to do |
|---|---|
| `ssh` says "Permission denied (publickey)" | You're on a different PC or the key wasn't added. In DigitalOcean open the droplet → **Access** → **Launch Droplet Console** to get in from the browser. |
| Browser says "can't reach this site" | DNS not ready yet (`nslookup` from step 5) or the record is wrong. Wait, then `docker compose restart caddy`. |
| Certificate or padlock error | `docker compose logs caddy | tail -30`. Usually DNS points elsewhere, the Cloudflare cloud is orange, or the firewall blocks 80/443. Fix it, then `docker compose restart caddy`. |
| "Bad Request (400)" | `DJANGO_ALLOWED_HOSTS` doesn't exactly match the address you typed. Fix `.env`, `docker compose up -d`. |
| "CSRF verification failed" on login | `DJANGO_CSRF_TRUSTED_ORIGINS` must be `https://` + your exact address. |
| `web` keeps restarting | `docker compose logs web | tail -50`. A typo in `.env` is the usual reason. |
| No "Upload lesson video" box | Bunny lines in `.env` still start with `#` or are empty. Fix, then `docker compose up -d`. |
| Video shows "403" or won't play | Token key in `.env` doesn't match Bunny's Security tab, or the address in Allowed Referrers is different from your LMS address. |
| Locked out of the owner account | `docker compose exec web python manage.py changepassword ramkiran` |
| Watch what's happening live | `docker compose logs -f web` (Ctrl+C to stop watching) |
