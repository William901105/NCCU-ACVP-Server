# NCCU ACVP Server Frontend

The frontend is the strict FIPS 203 / ML-KEM and FIPS 204 / ML-DSA ACVP client
surface. It obtains and stores a short-lived access token, creates registration
sessions, downloads prompt vector sets, accepts IUT responses and displays NIST
GenVal dispositions. After all vector sets finish validation, it downloads a
single complete test-session PDF report. It does not generate cryptographic
responses or expose server-side expected results.

For manual or vendor acceptance, use the repository Docker deployment described
in [`../DEPLOYMENT.md`](../DEPLOYMENT.md). Nginx then serves the frontend at
`http://127.0.0.1:8080` and proxies `/api` and `/acvp` to the internal engine.

For frontend development:

```bash
npm ci
npm run dev
```

The development API base URL defaults to `http://127.0.0.1:8000` and can be
configured with `VITE_API_BASE_URL`. The production Docker build intentionally
sets it to an empty string so requests use the same-origin Nginx proxy.

Run the frontend checks with:

```bash
npm test
npm run build
```
