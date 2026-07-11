# NCCU ACVP Server Frontend

The frontend is a strict ML-DSA ACVP client surface. It displays the fixed
workflow and execution backend, creates registration sessions, downloads vector
sets, accepts IUT responses, and reads NIST GenVal results.

`isSample` is the only ACVP runtime option. Sample vector sets may retrieve
expected results; non-sample sessions keep them server-side.

```bash
npm ci
npm run dev
```

The API base URL defaults to `http://127.0.0.1:8000` and can be configured with
`VITE_API_BASE_URL`.
