# Server Browser Access

This note captures how the server-hosted browser automation is accessed and operated on this machine.

## noVNC access

Public URL:

`http://151.241.228.232:6080/vnc.html?host=151.241.228.232&port=6080`

Important:
- `websockify` must be running.
- `6080/tcp` must be allowed through `ufw`.
- This is temporary operator access and should not be left open longer than needed.

Current session password example:

`JbzclbrYTVft`

Password file:

`/home/sitectl/.vnc/passwd`

## Start noVNC

```bash
ufw allow 6080/tcp comment 'temporary noVNC for site-control'
nohup websockify --web=/usr/share/novnc 6080 127.0.0.1:5900 >/tmp/novnc.log 2>&1 &
ss -ltnp | rg ':6080'
```

## Check noVNC

```bash
curl -I http://127.0.0.1:6080/vnc.html
```

Expected result:
- `HTTP/1.1 200 OK`

## Stop noVNC

```bash
pkill -f 'websockify --web=/usr/share/novnc 6080 127.0.0.1:5900' || true
```

Remove the temporary firewall rules as well.

## Hub token

```bash
TOKEN=$(awk -F= '/^SITECTL_TOKEN=/{print $2}' /etc/site-control-kit/hub.env)
cd /root/site-control-kit
```

## Basic browser control

List clients:

```bash
./.venv/bin/python -m webcontrol browser \
  --server http://127.0.0.1:8765 \
  --token "$TOKEN" \
  clients
```

List tabs:

```bash
./.venv/bin/python -m webcontrol browser \
  --server http://127.0.0.1:8765 \
  --token "$TOKEN" \
  tabs
```

Open a site:

```bash
./.venv/bin/python -m webcontrol browser \
  --server http://127.0.0.1:8765 \
  --token "$TOKEN" \
  open 'https://xiaozhi.me/'
```

Open a new tab:

```bash
./.venv/bin/python -m webcontrol browser \
  --server http://127.0.0.1:8765 \
  --token "$TOKEN" \
  new-tab 'https://xiaozhi.me/console/agents'
```

Read page text:

```bash
./.venv/bin/python -m webcontrol browser \
  --server http://127.0.0.1:8765 \
  --token "$TOKEN" \
  text body
```

Read page HTML:

```bash
./.venv/bin/python -m webcontrol browser \
  --server http://127.0.0.1:8765 \
  --token "$TOKEN" \
  html body
```

Click by text:

```bash
./.venv/bin/python -m webcontrol browser \
  --server http://127.0.0.1:8765 \
  --token "$TOKEN" \
  click-text 'Save'
```

Click by selector:

```bash
./.venv/bin/python -m webcontrol browser \
  --server http://127.0.0.1:8765 \
  --token "$TOKEN" \
  click 'button.ant-btn-primary[type="submit"]'
```

Fill a field:

```bash
./.venv/bin/python -m webcontrol browser \
  --server http://127.0.0.1:8765 \
  --token "$TOKEN" \
  fill '#form_item_assistantName' 'Макс'
```

Wait for an element:

```bash
./.venv/bin/python -m webcontrol browser \
  --server http://127.0.0.1:8765 \
  --token "$TOKEN" \
  wait '#form_item_character'
```

Take a screenshot:

```bash
./.venv/bin/python -m webcontrol browser \
  --server http://127.0.0.1:8765 \
  --token "$TOKEN" \
  screenshot --output /tmp/page.png
```

## Target a specific page

By URL pattern:

```bash
./.venv/bin/python -m webcontrol browser \
  --server http://127.0.0.1:8765 \
  --token "$TOKEN" \
  --url-pattern '/console/agents/1662279/config' \
  text body
```

By tab id:

```bash
./.venv/bin/python -m webcontrol browser \
  --server http://127.0.0.1:8765 \
  --token "$TOKEN" \
  --tab-id 206018391 \
  screenshot --output /tmp/tab.png
```

## Working pattern

1. Check that hub and Chrome are alive.
2. Read `TOKEN`.
3. Inspect current tabs.
4. Open the target site.
5. Read the page with `text body` or `html body`.
6. Identify selectors or button text.
7. Click, fill, save.
8. Re-read the page to confirm the change persisted.
9. Use noVNC only when human login or manual review is needed.
