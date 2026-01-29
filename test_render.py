import argparse
import pathlib
import requests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default="http://localhost:8000", help="Base URL of the API")
    parser.add_argument("--pt", required=True, type=pathlib.Path, help="Path to GVHMR .pt file")
    parser.add_argument("--robot", default="unitree_g1", help="Robot name")
    parser.add_argument("--out", default="out.mp4", type=pathlib.Path, help="Output mp4 path")
    parser.add_argument("--width", type=int, default=None, help="Render width override")
    parser.add_argument("--height", type=int, default=None, help="Render height override")
    args = parser.parse_args()

    if not args.pt.is_file():
        raise FileNotFoundError(f"Input .pt not found: {args.pt}")

    url = f"{args.server.rstrip('/')}/render"
    with args.pt.open("rb") as f:
        files = {"file": (args.pt.name, f, "application/octet-stream")}
        data = {"robot": args.robot}
        if args.width:
            data["width"] = str(args.width)
        if args.height:
            data["height"] = str(args.height)
        resp = requests.post(url, files=files, data=data, timeout=600)

    if resp.status_code != 200:
        raise SystemExit(f"Request failed: {resp.status_code} {resp.text}")

    args.out.write_bytes(resp.content)
    print(f"Saved video to {args.out}")


if __name__ == "__main__":
    main()
