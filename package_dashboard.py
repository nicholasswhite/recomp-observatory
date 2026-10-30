"""Package only the observer's explicit file list, never local target data."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

BASE=Path(__file__).resolve().parent
FILES=[
    '.gitattributes','.gitignore','LICENSE','VERSION','README.md','CHANGELOG.md','CONTRIBUTING.md','SECURITY.md','AGENTS.md',
    'Start Dashboard.cmd','Start Dashboard.ps1','server.py','workspace.py','adapters.py','collector.py',
    'folders.py','pathguard.py','artwork.py','ps3_metrics.py','export_progress.py','observatory.project.example.json',
    'package_dashboard.py','verify_package.py','test_artwork.py','test_collector.py','test_folder_routes.py',
    'test_folders.py','test_pathguard.py','test_progress.cjs','test_ps3_metrics.py','test_workspace.py','test_package.py',
    'public/index.html','public/app.js','public/workspace-ui.js','public/progress.js','public/ps3-details.js',
    'public/folders.js','public/branding.js','public/style.css','public/ps3-theme.css',
]

def package(output):
    with ZipFile(output,'w',compression=ZIP_DEFLATED) as archive:
        for relative in FILES:
            path=BASE/relative
            if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(BASE):
                raise ValueError(f'Unsafe or missing package member: {relative}')
            archive.write(path,'recomp-observatory/'+relative)
    return output

if __name__=='__main__':
    (BASE/'work').mkdir(exist_ok=True)
    print(package(BASE/'work/recomp-observatory.zip'))
