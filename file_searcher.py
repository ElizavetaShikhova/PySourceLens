from pathlib import Path

def get_files_in_directory(path: str | Path) -> list[Path]:
    path = Path(path)
    res = []
    try:
        for entry in path.iterdir():
            if entry.is_dir():
                res.extend(get_files_in_directory(entry))
            elif entry.is_file() and entry.suffix == '.py':
                res.append(entry)
    except PermissionError:
        pass
    
    return res

if __name__ == "__main__":
    print(get_files_in_directory())