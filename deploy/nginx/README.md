# nginx config (EC2 reverse proxy)

`silverlake.conf` is a mirror of `/etc/nginx/sites-available/silverlake` on the production EC2
box. It's **not** deployed automatically by CI — this project has no IaC/Ansible for the box
itself (see the README's own Deployment section), so this file exists purely so nginx changes go
through the same review/diff/history as everything else, instead of being edited blind directly
on the server (which is how this file's own git history started).

## Pulling the live config down (to confirm this file is still in sync, or before editing)

```
scp -i <path-to-ec2-key.pem> ubuntu@<EC2_HOST>:/etc/nginx/sites-available/silverlake deploy/nginx/silverlake.conf
```

## Applying a change

1. Edit `deploy/nginx/silverlake.conf` in this repo, commit it like any other change.
2. Copy it to the box and reload:
   ```
   scp -i <path-to-ec2-key.pem> deploy/nginx/silverlake.conf ubuntu@<EC2_HOST>:/tmp/silverlake.conf
   ssh -i <path-to-ec2-key.pem> ubuntu@<EC2_HOST> "sudo cp /tmp/silverlake.conf /etc/nginx/sites-available/silverlake && sudo nginx -t && sudo systemctl reload nginx"
   ```
   `nginx -t` validates syntax *before* `reload` touches the running server - never skip it.
3. Verify live (e.g. `curl -sI https://silverlakecarentals.com/` for headers, or exercise
   whatever the change actually affects) before considering it done.

## Certbot-managed blocks

The `listen 443 ssl` / `listen 80` blocks and their `ssl_certificate*` lines are stamped
`# managed by Certbot` - renewal (`certbot renew`, on a cron/systemd timer on the box) may
rewrite those specific lines. Re-pull the live config after a renewal to keep this file honest,
rather than assuming it's still byte-for-byte accurate forever.
