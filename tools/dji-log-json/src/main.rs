//! Envoltorio mínimo sobre dji-log-parser (MIT): lee un DJIFlightRecord .txt y
//! escribe JSON {version, details, frames} en stdout.
//!
//! Uso: dji-log-json <log.txt> [--keychains <cache.json>]
//! - La clave de DJI se lee de la variable de entorno DJI_API_KEY (nunca por argumento,
//!   para que no quede en el historial ni en `ps`).
//! - Con --keychains, las llaves se guardan tras el primer pedido y se reutilizan sin red.
//! - A DJI sólo viaja el KeychainsRequest (versión, departamento y las llaves cifradas
//!   del propio log); la telemetría no sale del equipo.
use std::{env, fs, process::exit};

use dji_log_parser::DJILog;

fn fail(code: &str, msg: &str) -> ! {
    eprintln!("{}", serde_json::json!({ "error": code, "message": msg }));
    exit(2);
}

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() < 2 {
        fail("usage", "dji-log-json <log.txt> [--keychains <cache.json>]");
    }
    let path = &args[1];
    let cache = args
        .iter()
        .position(|a| a == "--keychains")
        .and_then(|i| args.get(i + 1))
        .cloned();

    let bytes = fs::read(path).unwrap_or_else(|e| fail("read_error", &e.to_string()));
    let parser = DJILog::from_bytes(bytes).unwrap_or_else(|e| fail("unsupported_format", &e.to_string()));

    let keychains = if parser.version >= 13 {
        let cached = cache
            .as_ref()
            .and_then(|c| fs::read_to_string(c).ok())
            .and_then(|s| serde_json::from_str(&s).ok());
        match cached {
            Some(k) => Some(k),
            None => {
                let key = env::var("DJI_API_KEY")
                    .ok()
                    .filter(|k| !k.trim().is_empty())
                    .unwrap_or_else(|| fail("missing_api_key", "DJI_API_KEY is not set"));
                let k = parser
                    .fetch_keychains(key.trim())
                    .unwrap_or_else(|e| fail("keychain_error", &e.to_string()));
                if let Some(c) = &cache {
                    let _ = fs::write(c, serde_json::to_string(&k).unwrap_or_default());
                }
                Some(k)
            }
        }
    } else {
        None
    };

    let frames = parser
        .frames(keychains)
        .unwrap_or_else(|e| fail("incomplete", &e.to_string()));
    let out = serde_json::json!({
        "version": parser.version,
        "details": parser.details,
        "frames": frames,
    });
    println!("{}", out);
}
