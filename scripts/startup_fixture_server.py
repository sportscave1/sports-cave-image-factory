"""Isolated fixture only. No production server import or business API routes."""
import argparse
import ipaddress
import logging
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def deny_external_network(event, args):
    if event != "socket.connect":
        return
    address = args[1]
    if isinstance(address, tuple):
        try:
            local = ipaddress.ip_address(address[0]).is_loopback
        except ValueError:
            local = address[0] == "localhost"
        if not local:
            raise PermissionError("Offline startup fixture blocks external connections.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--fixture", choices=["startup_measurement", "page_loading_measurement"],
                        default="startup_measurement")
    args = parser.parse_args()
    sys.addaudithook(deny_external_network)
    logging.basicConfig(level=logging.INFO)
    from startup_performance import StartupTrace, StartupTimingMiddleware
    trace = StartupTrace()
    import streamlit.config as config
    config.set_option("browser.gatherUsageStats", False)
    config.set_option("server.fileWatcherType", "none")
    config.set_option("secrets.files", [])
    from streamlit.web.server.starlette import App
    from app_branding import InitialDocumentBrandingMiddleware
    from static_asset_compression import StaticAssetCompression
    import uvicorn
    trace.mark("fixture_imports_done")
    app = StartupTimingMiddleware(InitialDocumentBrandingMiddleware(StaticAssetCompression(
        App(str(ROOT / "tests/fixtures" / (args.fixture + ".py"))))), trace=trace)
    trace.mark("fixture_assembled")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
