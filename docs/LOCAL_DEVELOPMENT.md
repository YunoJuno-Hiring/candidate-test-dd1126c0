# Local Development: Running Services and Tests

This guide covers how to run the stack locally and how to run each test pack.

- **Recommended: the nix dev shell.** The project pins its toolchain with a nix flake. Enter the shell, then use the `task ...` commands from `Taskfile.dist.yml` (sections 1 and 3).
- **Fallback: Docker only.** For machines without nix. The backend runs in a uv container (section 4). The backend test command was verified on 2026-10-17.

All commands run from the repository root unless stated otherwise.

## 1. Prerequisites and the nix dev shell

This project pins its toolchain with nix. `flake.nix` defines a dev shell, `flake.lock` locks the nixpkgs snapshot, and `.envrc` (`use flake`) lets direnv load it. Use this shell rather than installing the tools yourself. The repository has no other pin files (no `.python-version`, `.nvmrc`, `mise.toml` or `packageManager` field).

| Tool | Provided by | Version |
|---|---|---|
| Python | nix (`python311`) | 3.11 |
| uv | nix (`uv`) | from `flake.lock` (README states 0.11) |
| Node.js | nix (`nodejs-slim_24`) | 24, **without npm** by design |
| pnpm | nix (`pnpm`) | from `flake.lock` (README states 10.33; lockfile needs 9 or later) |
| Task | nix (`go-task`) | 3 |
| Docker + Docker Compose | **not in the flake**; install separately | any modern |

`flake.nix` states the package manager policy: "We use pnpm exclusively; npm's post-install script behaviour is considered a security risk on this project."

### 1.1 Install Nix (one time, macOS)

The Determinate Systems installer is the simplest on macOS, because it enables flakes by default:

```bash
curl -fsSL https://install.determinate.systems/nix | sh -s -- install
```

- It asks for `sudo` and creates a separate `/nix` APFS volume.
- Open a new terminal afterwards and check the install with `nix --version`.
- To uninstall later, run `/nix/nix-installer uninstall`.

The official installer (`sh <(curl -L https://nixos.org/nix/install)`) also works. With it, enable flakes yourself by adding `experimental-features = nix-command flakes` to `~/.config/nix/nix.conf`.

Install Docker separately, because the flake does not provide it: `brew install --cask docker`. Start Docker Desktop once after installing it.

### 1.2 Enter the dev shell

```bash
cd <repository root>
nix develop
```

- The first run downloads the pinned toolchain.
- The shell then prints a banner with the Python, uv, Node and pnpm versions (`shellHook` in `flake.nix`).
- All `task ...` commands in section 3 run inside this shell.
- Run `exit` to leave the shell.

**Optional: load the shell automatically with direnv.** Install direnv with `brew install direnv`, then run `direnv allow` once in the repository root. direnv also needs its hook in your shell startup file (`eval "$(direnv hook zsh)"` in `~/.zshrc`). If you prefer not to edit shell config, run `nix develop` by hand instead.

### 1.3 Notes

- **Webhook receiver:** `task receiver` runs `npm install`, which fails inside the nix shell because `nodejs-slim_24` has no npm. Use the Docker route in section 4.4 instead.
- **Versions:** they come from the nixpkgs snapshot in `flake.lock`. Python 3.11 and Node 24 are fixed by package name. uv and pnpm may not match the README's 0.11 / 10.33 exactly.
- **Existing `backend/.venv`:** if the venv was created outside nix on the wrong Python, see the first gotcha in section 6.
- **Not verified:** nix was not installed on this machine on 2026-10-17, so the commands in this section were not run.

## 2. Services and ports

| Service | URL / port | Started by |
|---|---|---|
| Frontend (Vite) | http://localhost:3000 | `task frontend` |
| Backend API | http://localhost:8000/api/ | `task backend` |
| Django admin | http://localhost:8000/admin/ | `task backend` |
| Postgres 18 | `localhost:5432`, db/user/password `yunojuno` | `task up` (docker-compose `db`) |
| Mailpit | UI http://localhost:8025, SMTP `localhost:1025` | `task up` (docker-compose `mailpit`) |
| Webhook receiver | http://localhost:8027 (UI), `POST /hook` | Docker (section 4.4) or `task receiver`; not part of docker-compose |

The Vite dev server proxies `/api` to `http://localhost:8000` (`frontend/vite.config.ts`).

Seed login accounts are listed in [`seed_users.md`](../seed_users.md).

## 3. Standard route (Taskfile)

```bash
task up          # docker compose up -d  -> Postgres + Mailpit
task seed        # migrate + seed (run once after `task up`)
task backend     # Django dev server on :8000
task frontend    # Vite dev server on :3000
```

Run these inside the nix shell (`nix develop`). Run `task backend` and `task frontend` in separate terminals. For the webhook receiver, use the Docker route in section 4.4, because `task receiver` needs npm.

Install frontend dependencies before the first run:

```bash
cd frontend && pnpm install
```

`uv run` syncs backend dependencies from `backend/uv.lock` automatically. It creates `backend/.venv` on first use.

## 4. Fallback route (no nix)

### 4.1 Supporting services

```bash
docker compose up -d
docker compose ps        # db and mailpit should be Up
```

### 4.2 Backend in a uv container

This runs the backend inside the official uv image with Python 3.11. Dependencies are installed into the container from `uv.lock`, so nothing is written to the host. A named volume (`yj-uv-cache`) caches downloads between runs.

Define this helper once per shell (run it from the repository root):

```bash
yj_backend() {
  docker run --rm -it \
    -v "$PWD/backend:/app" -w /app \
    -v yj-uv-cache:/root/.cache/uv \
    -e UV_PROJECT_ENVIRONMENT=/venv \
    -e PYTHONDONTWRITEBYTECODE=1 \
    -e DB_HOST=host.docker.internal \
    -e EMAIL_HOST=host.docker.internal \
    -e DEBUG=True \
    ghcr.io/astral-sh/uv:python3.11-bookworm-slim "$@"
}
```

Migrate and seed (once):

```bash
yj_backend sh -c "uv run --frozen python manage.py migrate --noinput && uv run --frozen python manage.py seed"
```

Start the dev server on http://localhost:8000. This needs a published port, so it uses the full command:

```bash
docker run --rm -it -p 8000:8000 \
  -v "$PWD/backend:/app" -w /app \
  -v yj-uv-cache:/root/.cache/uv \
  -e UV_PROJECT_ENVIRONMENT=/venv -e PYTHONDONTWRITEBYTECODE=1 \
  -e DB_HOST=host.docker.internal -e EMAIL_HOST=host.docker.internal -e DEBUG=True \
  ghcr.io/astral-sh/uv:python3.11-bookworm-slim \
  uv run --frozen python manage.py runserver 0.0.0.0:8000
```

`host.docker.internal` lets the container reach Postgres and Mailpit published on the host. This works with Docker Desktop. On Linux, add `--add-host=host.docker.internal:host-gateway`.

### 4.3 Frontend

```bash
cd frontend
corepack pnpm install     # corepack ships with Node 24
corepack pnpm dev         # http://localhost:3000
```

If `frontend/node_modules` already exists, you can call the binaries directly instead: `./node_modules/.bin/vite --host 0.0.0.0 --port 3000`.

### 4.4 Webhook receiver

Preferred: run it with Docker. npm then runs only inside the image build, which respects the project's pnpm-only policy (section 1).

```bash
docker build -t yj-webhook-receiver services/webhook-receiver
docker run --rm -p 8027:8027 yj-webhook-receiver   # http://localhost:8027
```

Taskfile route: `task receiver` runs `npm install --omit=dev` and then `node index.js` on the host. This is the only place in the repository that uses npm. It works only with a Node install that includes npm, so it does not work inside the nix shell.

## 5. Running the test packs

### 5.1 Backend (pytest + pytest-django)

The backend tests need Postgres running (`task up` or `docker compose up -d`). pytest-django creates and drops a `test_yunojuno` database.

Standard route:

```bash
task test                                    # whole suite
cd backend
uv run pytest                                # whole suite
uv run pytest contracts                      # one app
uv run pytest contracts/tests/test_timesheets.py          # one file
uv run pytest -k reject                      # tests whose name matches "reject"
uv run pytest contracts/tests/test_timesheets.py::test_patch_approve  # one test
uv run pytest -x -vv                         # stop on first failure, verbose
```

Fallback route (repository mounted read-only, no cache files written):

```bash
docker run --rm \
  -v "$PWD/backend:/app:ro" -w /app \
  -v yj-uv-cache:/root/.cache/uv \
  -e UV_PROJECT_ENVIRONMENT=/venv -e PYTHONDONTWRITEBYTECODE=1 \
  -e DB_HOST=host.docker.internal \
  ghcr.io/astral-sh/uv:python3.11-bookworm-slim \
  uv run --frozen pytest -p no:cacheprovider -q
```

To run a narrower selection, add arguments after `-q`, for example `contracts -k reject`.

Test conventions: function-style tests marked `@pytest.mark.django_db`, kept in `<app>/tests/test_*.py`. Shared fixtures (`admin_client`, `freelancer_client`, `active_contract`, `other_contract`, `submitted_entry` and others) live in `backend/conftest.py`.

### 5.2 Backend checks

```bash
cd backend
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run   # fails if a migration is missing
```

For the fallback route, run the same checks with the helper, for example `yj_backend uv run --frozen python manage.py check`.

### 5.3 Frontend

```bash
cd frontend
./node_modules/.bin/tsc --noEmit     # type check (strict mode)
pnpm build                           # tsc + vite build into frontend/dist (gitignored); without nix: corepack pnpm build
```

**No frontend unit test runner is configured** (no vitest or jest in `package.json`). **No linter or formatter is configured** for either the frontend or the backend. Frontend verification is therefore limited to the type check and the build.

### 5.4 Baseline results (2026-10-17, before any task changes)

| Check | Result |
|---|---|
| Backend pytest (fallback container) | 41 passed |
| `manage.py check` | No issues |
| `makemigrations --check --dry-run` | No changes detected |
| Frontend `tsc --noEmit` | Passed |
| Frontend `tsc && vite build` | Passed |

## 6. Gotchas

- **`task backend` fails with `psycopg-binary` and `cp315`.** The exact error is:
  `error: Distribution psycopg-binary==3.3.4 ... can't be installed because it doesn't have a source distribution or wheel for the current platform`, with the hint `You're using CPython 3.15 (cp315), but psycopg-binary (v3.3.4) only has wheels with ... cp311, cp312, cp313, cp314`.
  The cause is that uv ran outside the nix shell and chose the newest Python installed. Run it inside `nix develop`, or recreate the venv on 3.11:
  ```bash
  rm -rf backend/.venv                     # stale environment built on the wrong Python (gitignored)
  (cd backend && uv sync --python 3.11)
  task backend
  ```
- **The webhook receiver is not in `docker-compose.yml`.** The hostname `webhook-receiver:8027` resolves only inside a Docker network that contains the receiver. When the backend runs on the host, target `http://localhost:8027/hook`. When the backend runs in the fallback container, target `http://host.docker.internal:8027/hook`.
- **`DEBUG` defaults to `False`** (`backend/config/settings.py`). Set `DEBUG=True` locally so Django admin static files and debug error pages work.
- **Email** uses the SMTP backend pointed at `EMAIL_HOST:1025`, so every message lands in Mailpit at http://localhost:8025. In tests, pytest-django's `mailoutbox` fixture switches to Django's `locmem` backend automatically.
- **Seeding is idempotent** (`get_or_create` / `update_or_create`). Entry statuses depend on the current date, so re-seeding later shifts which months are approved, submitted or draft.
- **Auth** uses DRF token auth. `POST /api/auth/login/` with `{email, password}` returns a token. Send it as `Authorization: Token <key>`.
