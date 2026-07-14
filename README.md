<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://via.placeholder.com/120x120/1B2A4A/2EC4B6?text=AO">
    <img src="https://via.placeholder.com/120x120/1B2A4A/2EC4B6?text=AO" alt="AeroOps Desk" width="120" height="120">
  </picture>
</p>

<h1 align="center">AeroOps Desk</h1>

<p align="center">
  <strong>RPA Operations Console</strong><br>
  Local control panel for managing RPA fleet operations, crew qualifications, compliance, and maintenance.
</p>

<p align="center">
  <a href="#-features">Features</a> •
  <a href="#-architecture">Architecture</a> •
  <a href="#-getting-started">Getting Started</a> •
  <a href="#-project-structure">Structure</a> •
  <a href="#-development">Development</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.12-blue?style=flat&logo=python&logoColor=white" alt="Python 3.12">
  <img src="https://img.shields.io/badge/django-6.0-092E20?style=flat&logo=django&logoColor=white" alt="Django 6.0">
  <img src="https://img.shields.io/badge/license-MIT-green?style=flat" alt="MIT License">
  <img src="https://img.shields.io/badge/status-alpha-yellow?style=flat" alt="Status: Alpha">
</p>

<br>

## 💡 About

**AeroOps Desk** was born from the operational reality of RPA (Remotely Piloted Aircraft) fleet management: spreadsheets everywhere, expiring credentials tracked in email threads, maintenance records scattered across folders, and flight permissions cobbled together at the last minute.

This is a **local-first operations console** — not a SaaS platform, not a cloud dashboard. It lives on the operator's machine, talks to a local SQLite database, and keeps operational data completely under the operator's control. The database, documents, and backups live outside the repository, on a separate data directory, so the code can be updated, rolled back, or even reinstalled without touching a single operational record.

The name reflects its purpose: **Aero** (aviation), **Ops** (operations), **Desk** (your personal workspace). A tool for the person who needs to know, at a glance, what's airworthy, who's current, what's expiring, and what's next.

<br>

## ✈ Features

| Domain | Capabilities |
|--------|-------------|
| **Registry** | Cost centers, aircraft fleet, operators, assignments, and qualifications — all with archival instead of deletion |
| **Compliance** | Document management with version replacement, configurable alert rules, and automatic expiration tracking |
| **Operations** | Flight permission workflow (request → approve → complete), flight record logging |
| **Maintenance** | Scheduled and unscheduled maintenance records, status history, and technical log |
| **Workboard** | Personal Kanban with stages, task priorities, and operator assignment |
| **Dashboard** | Executive summary with counts, upcoming expirations, and task distribution |
| **Backup** | OneDrive-safe SQLite snapshots via PowerShell automation |

<br>

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    AeroOps Desk (Django)                     │
│                                                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │
│  │ Registry │ │Compliance│ │Operations│ │  Maintenance   │  │
│  │  ─────── │ │ ──────── │ │ ──────── │ │  ────────────  │  │
│  │ Aircraft │ │Documents │ │Permits   │ │  Records       │  │
│  │Operator  │ │Alerts    │ │Flights   │ │  History       │  │
│  │CostCenter│ │Rules     │ │          │ │                │  │
│  └─────┬────┘ └────┬─────┘ └────┬─────┘ └───────┬────────┘  │
│        └───────────┴────────────┴───────────────┘           │
│                            │                                │
│                    ┌───────┴────────┐                        │
│                    │   Workboard    │                        │
│                    │  (Kanban)      │                        │
│                    └───────┬────────┘                        │
│                            │                                │
│                    ┌───────┴────────┐                        │
│                    │   Dashboard    │                        │
│                    │  (Read-only)   │                        │
│                    └────────────────┘                        │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                Django REST API (Future)               │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
         ↕                                          ↕
    ┌─────────┐                           ┌──────────────────┐
    │SQLite   │                           │  AeroOpsDesk_Data│
    │Database │                           │ ──────────────── │
    │(local)  │                           │ documents/       │
    └─────────┘                           │ backups/         │
                                          │ exports/         │
                                          │ logs/            │
                                          └──────────────────┘
```

### Separation of Code & Data

A core design decision: **code and data never mix**.

```
D:\I+D\
├── aero-ops-desk\           ← Code (git repository)
│   ├── apps/
│   ├── config/
│   ├── templates/
│   ├── manage.py
│   └── ...
│
└── AeroOpsDesk_Data\        ← Data (NOT in git)
    ├── db/aero_ops.sqlite3   ← Active database
    ├── documents/             ← Uploaded files
    ├── backups/               ← SQLite snapshots
    ├── exports/               ← Generated reports
    └── logs/                  ← Application logs
```

This means you can `git pull`, reinstall, or switch branches without risking your operational data. Backups go to OneDrive as closed snapshots — the live SQLite database is never directly synced.

<br>

## 🚀 Getting Started

### Prerequisites

- **Python 3.12+**
- **PowerShell 7+** (for automation scripts)
- **Git** (for updates)

### Installation

```powershell
# 1. Clone the repository
git clone https://github.com/DovaCrii/aero-ops-desk.git
cd aero-ops-desk

# 2. Run setup (creates .venv, installs deps, migrates database)
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1

# 3. Create your admin user
.\.venv\Scripts\python.exe manage.py createsuperuser

# 4. Start the server
powershell -ExecutionPolicy Bypass -File .\scripts\run.ps1
```

The app opens at [http://127.0.0.1:8000](http://127.0.0.1:8000).

### Data Directory

The first time you run setup, `D:\I+D\AeroOpsDesk_Data\` is created automatically. You can change this by editing `DOCUMENTS_DIR` and `DB_PATH` in `.env`.

<br>

## 📁 Project Structure

```
aero-ops-desk/
├── apps/
│   ├── core/           # Base model, backup engine, shared mixins
│   ├── registry/       # Cost centers, aircraft, operators
│   ├── compliance/     # Documents, alerts, expiration rules
│   ├── operations/     # Flight permissions and flight records
│   ├── maintenance/    # Maintenance records and status history
│   ├── workboard/      # Personal Kanban workflow
│   └── dashboard/      # Executive summary view
├── config/
│   ├── settings/       # Split settings: base, dev, prod
│   ├── urls.py         # Root URL configuration
│   └── wsgi.py         # WSGI entry point
├── templates/          # Bootstrap 5 responsive templates
├── static/             # CSS and client-side assets
├── scripts/            # PowerShell automation
├── prompts/            # OpenCode continuation prompts
├── openspec/           # SDD specification artifacts
├── docs/               # Additional documentation
└── manage.py           # Django management entry point
```

<br>

## 🛠 Development

This project uses [Spec-Driven Development (SDD)](https://github.com/gentleman-programming/gentle-ai) through OpenCode. Changes are planned in `openspec/` before implementation:

```
openspec/
├── config.yaml           # Project configuration
├── specs/                # Domain specifications
└── changes/              # Active and archived changes
    ├── phase1-document-mgmt/
    │   ├── proposal.md   # What and why
    │   ├── spec.md       # Functional requirements
    │   ├── design.md     # Technical design
    │   └── tasks.md      # Implementation tasks
    └── archive/          # Completed changes
```

### Useful Commands

```powershell
# Run checks
python manage.py check

# Run tests
python manage.py test

# Generate alerts
python manage.py generate_alerts

# Manual backup
powershell -ExecutionPolicy Bypass -File .\scripts\backup.ps1
```

<br>

## 📜 License

Distributed under the **MIT License**. See [LICENSE](LICENSE) for details.

---

<p align="center">
  <sub>Built with ❤️ for RPA operators who need their tools to just work.</sub>
</p>
