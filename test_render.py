import argparse
import pathlib
import requests


def parse_outputs(raw: str) -> list[str]:
    tokens = [token.strip().lower() for token in raw.split(",") if token.strip()]
    expanded = []
    for token in tokens:
        if token == "both":
            expanded.extend(["mp4", "traj"])
        else:
            expanded.append(token)
    result = []
    for token in expanded:
        if token not in result:
            result.append(token)
    if not result:
        raise ValueError("No valid outputs were provided")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default="http://localhost:8000", help="Base URL of the API")
    parser.add_argument(
        "--endpoint",
        choices=["process", "render"],
        default="process",
        help="API endpoint path",
    )
    parser.add_argument("--pt", required=True, type=pathlib.Path, help="Path to GVHMR .pt file")
    parser.add_argument("--input_type", default="gvhmr", help="Input type for /process")
    parser.add_argument(
        "--coord_fix",
        default="none",
        choices=["none", "yup_to_zup"],
        help="Coordinate correction (primarily for smplx_npz input)",
    )
    parser.add_argument("--robot", default="unitree_g1", help="Robot name")
    parser.add_argument(
        "--outputs",
        default=None,
        help="Comma-separated outputs, e.g. mp4,csv,traj",
    )
    parser.add_argument("--format", default=None, help="Legacy alias for a single output")
    parser.add_argument("--out", default=None, type=pathlib.Path, help="Output file path")
    parser.add_argument("--width", type=int, default=None, help="Render width override")
    parser.add_argument("--height", type=int, default=None, help="Render height override")
    args = parser.parse_args()

    if not args.pt.is_file():
        raise FileNotFoundError(f"Input .pt not found: {args.pt}")
    outputs_raw = args.outputs if args.outputs else (args.format if args.format else "mp4")
    outputs = parse_outputs(outputs_raw)

    url = f"{args.server.rstrip('/')}/{args.endpoint}"
    if args.out is None:
        if len(outputs) > 1:
            args.out = pathlib.Path("out.zip")
        elif outputs[0] == "mp4":
            args.out = pathlib.Path("out.mp4")
        elif outputs[0] == "traj":
            args.out = pathlib.Path("out.pkl")
        elif outputs[0] == "csv":
            args.out = pathlib.Path("out.csv")
        else:
            args.out = pathlib.Path("out.bin")

    with args.pt.open("rb") as f:
        files = {"file": (args.pt.name, f, "application/octet-stream")}
        data = {"robot": args.robot, "output_formats": ",".join(outputs)}
        if args.endpoint == "process":
            data["input_type"] = args.input_type
            data["coord_fix"] = args.coord_fix
        if args.width:
            data["width"] = str(args.width)
        if args.height:
            data["height"] = str(args.height)
        resp = requests.post(url, files=files, data=data, timeout=600)

    if resp.status_code != 200:
        raise SystemExit(f"Request failed: {resp.status_code} {resp.text}")

    args.out.write_bytes(resp.content)
    print(f"Saved output to {args.out}")


if __name__ == "__main__":
    main()
