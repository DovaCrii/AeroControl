"""La revisión de privacidad (`tools/kit/privacy_scan.py`) detecta lo que dice y no se debilita.

El repositorio es **público** y el CI depende de este escáner: una regla que deja de detectar es
una fuga que nadie ve. Estas pruebas fijan qué detecta cada regla, que una excepción sólo vale en
su archivo, y que la configuración no vuelve a llenarse de comodines (el defecto que `LV-306`
encontró al revisarla: `apps/core/test*` eximía la regla de RUT de todas las pruebas del paquete).
"""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "kit" / "privacy_scan.py"
CONFIG = ROOT / ".privacy-scan.json"

# Los textos que activan las reglas se arman en ejecución: si el código fuente los tuviera literales,
# el propio escáner marcaría este archivo (le pasó: antes de versionarlo, el gate lo daba por limpio).
REAL_EMAIL = "persona@" + "empresa-real.cl"
INSTITUTION_EMAIL = "ayuda@" + "institucion.gob.cl"
RUT_DOTTED = "12.345." + "678-5"
RUT_PLAIN = "12345678" + "-5"
RUT_K = "9.876." + "543-K"
PRIVATE_KEY_HEADER = "-----BEGIN RSA " + "PRIVATE KEY-----"

spec = importlib.util.spec_from_file_location("privacy_scan", SCRIPT)
privacy_scan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(privacy_scan)


def _scan(tmp_path, files, config=None):
    for name, content in files.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return privacy_scan.scan(tmp_path, config or {}, files=list(files))


class TestWhatItDetects:
    def test_a_real_looking_email_domain(self, tmp_path):
        problems = _scan(tmp_path, {"a.py": f"x = '{REAL_EMAIL}'\n"})

        assert any(p.startswith("email:") for p in problems)

    @pytest.mark.parametrize(
        "address", ["a@example.com", "a@example.org", "a@localhost", "a@algo.example"]
    )
    def test_example_addresses_are_fine(self, tmp_path, address):
        assert _scan(tmp_path, {"a.py": f"x = '{address}'\n"}) == []

    @pytest.mark.parametrize(
        "secret",
        [
            "nvapi-" + "A" * 24,
            "sk-" + "b" * 24,
            "AKIA" + "ABCDEFGHIJKLMNOP",
            PRIVATE_KEY_HEADER,
        ],
    )
    def test_keys_and_private_key_blocks(self, tmp_path, secret):
        assert _scan(tmp_path, {"a.py": f"KEY = '{secret}'\n"})

    def test_a_short_token_is_not_a_key(self, tmp_path):
        assert _scan(tmp_path, {"a.py": "x = 'nvapi-corta'\n"}) == []

    @pytest.mark.parametrize("rut", [RUT_DOTTED, RUT_PLAIN, RUT_K])
    def test_chilean_rut_with_or_without_dots(self, tmp_path, rut):
        problems = _scan(tmp_path, {"a.py": f"rut = '{rut}'\n"})

        assert any(p.startswith("rut:") for p in problems)

    def test_ordinary_numbers_are_not_a_rut(self, tmp_path):
        assert (
            _scan(tmp_path, {"a.py": "n = 1234567\nphone = '+56 2 2722 5000'\n"}) == []
        )

    def test_path_rules(self):
        assert privacy_scan.check_path("private/datos.csv")
        assert privacy_scan.check_path(".env")
        assert privacy_scan.check_path("config/.env.production")
        assert privacy_scan.check_path("--basura.txt")
        assert privacy_scan.check_path(".env.example") == []
        assert privacy_scan.check_path("apps/core/models.py") == []


class TestExceptions:
    def test_an_allowed_domain_is_accepted(self, tmp_path):
        files = {"a.py": f"x = '{INSTITUTION_EMAIL}'\n"}

        assert _scan(tmp_path, files)
        assert (
            _scan(tmp_path, files, {"allow_email_domains": ["institucion.gob.cl"]})
            == []
        )

    def test_a_rule_exception_only_applies_to_its_own_file(self, tmp_path):
        files = {
            "uno.py": f"rut = '{RUT_DOTTED}'\n",
            "dos.py": f"rut = '{RUT_DOTTED}'\n",
        }
        config = {"allow_rules": {"uno.py": ["rut"]}}

        problems = _scan(tmp_path, files, config)

        assert any("dos.py" in p for p in problems)
        assert not any("uno.py" in p for p in problems)

    def test_an_exception_for_one_rule_does_not_hide_another(self, tmp_path):
        files = {"uno.py": f"rut = '{RUT_DOTTED}'\nk = 'sk-" + "c" * 24 + "'\n"}

        problems = _scan(tmp_path, files, {"allow_rules": {"uno.py": ["rut"]}})

        assert any(p.startswith("sk:") for p in problems)

    def test_allowed_paths_are_not_examined(self, tmp_path):
        files = {"vendor/x.js": f"rut = '{RUT_DOTTED}'\n"}

        assert _scan(tmp_path, files, {"allow_paths": ["vendor/*"]}) == []


class TestTheCommandLine:
    def test_it_fails_with_findings_and_passes_without(
        self, tmp_path, capsys, monkeypatch
    ):
        monkeypatch.setattr(privacy_scan, "tracked_files", lambda root: ["a.py"])
        (tmp_path / "a.py").write_text(f"rut = '{RUT_DOTTED}'\n", encoding="utf-8")

        assert privacy_scan.main(["--root", str(tmp_path)]) == 1
        assert "FALLÓ" in capsys.readouterr().out

        (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")

        assert privacy_scan.main(["--root", str(tmp_path)]) == 0


class TestTheRepositoryConfiguration:
    def test_the_rule_exceptions_name_exact_files_never_globs(self):
        """«Las reglas no se debilitan»: una excepción por archivo, nunca por comodín."""
        config = json.loads(CONFIG.read_text(encoding="utf-8"))

        wildcards = [pattern for pattern in config["allow_rules"] if "*" in pattern]

        assert wildcards == []

    def test_every_excepted_file_exists(self):
        """Una excepción sobre un archivo que ya no existe es una puerta abierta sin motivo."""
        config = json.loads(CONFIG.read_text(encoding="utf-8"))

        missing = [path for path in config["allow_rules"] if not (ROOT / path).exists()]

        assert missing == []

    def test_no_broad_domain_is_allowed(self):
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        broad = {"gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "jej.cl"}

        assert not broad & {d.lower() for d in config["allow_email_domains"]}
