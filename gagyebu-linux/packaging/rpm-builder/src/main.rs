//! 우리집 가계부 (리눅스판) .rpm 만들기 — rpmbuild 없이 rpm 라이브러리로 직접 작성
//!   rpm-builder build <stage폴더> <버전> <출력.rpm>   (stage = packaging/build-deb.sh 가 만든 배치)
//!   rpm-builder show <파일.rpm>                       (만든 rpm 내용 확인)
use std::fs;
use std::path::{Path, PathBuf};

use rpm::{CompressionType, Dependency, FileMode, FileOptions, PackageBuilder, Scriptlet};

/// 스크립트 해석기를 /bin/sh 로 명시 (rpmbuild 가 만드는 패키지와 같게)
fn sh(script: &str) -> Scriptlet {
    Scriptlet::new(script).prog(vec!["/bin/sh"])
}

const PKG: &str = "gagyebu-linux";
/// 이 패키지가 소유하는 폴더 (지울 때 함께 지워짐). /usr/bin 같은 시스템 폴더는 소유하지 않음.
const OWNED_DIRS: [&str; 2] = ["/usr/share/gagyebu-linux", "/usr/share/doc/gagyebu-linux"];

fn walk(root: &Path, dir: &Path, files: &mut Vec<PathBuf>, dirs: &mut Vec<PathBuf>) {
    let mut entries: Vec<_> = fs::read_dir(dir).expect("read_dir").map(|e| e.unwrap().path()).collect();
    entries.sort();
    for p in entries {
        if p.is_dir() {
            dirs.push(p.clone());
            walk(root, &p, files, dirs);
        } else {
            files.push(p);
        }
    }
}

fn build(stage: &Path, version: &str, out: &Path) -> Result<(), Box<dyn std::error::Error>> {
    let empty = std::env::temp_dir().join("gagyebu-rpm-empty");
    fs::write(&empty, b"")?;
    let mut b = PackageBuilder::new(PKG, version, "LicenseRef-gagyebu-personal AND MIT", "noarch",
                                    "우리집 가계부 (리눅스판) - 가계부·자산·일정 관리")
        .release("1")
        .description("윈도우용 '우리집 가계부 v5.75'를 대체하는 리눅스 프로그램입니다. 가계부(잔액·검색·결산 보고서·그래프·\
                      예산·예약 자동입력), 자산관리(통장·카드·증권·보험·부동산), 일정(음력·기념일), 주소록·일기장·메모장을 \
                      지원하며 윈도우판 data 폴더(*.mdb)를 가져올 수 있습니다(mdbtools 필요). 데이터는 사용자별로 \
                      ~/.local/share/gagyebu 에 저장되며 패키지를 지워도 남습니다.")
        .group("Applications/Office")
        .compression(CompressionType::Gzip)
        .requires(Dependency::any("python3"))
        .requires(Dependency::any("python3-pyqt6"))
        .recommends(Dependency::any("mdbtools"))
        .recommends(Dependency::any("qt6-qtsvg"))
        .recommends(Dependency::any("qt6-qttranslations"))
        // 지우기 전: 실행 중 생긴 파이썬 캐시 정리 (패키지 파일이 아니라서)
        .pre_uninstall_script(sh("find /usr/share/gagyebu-linux -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || :"))
        .post_install_script(sh("command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q /usr/share/applications || :\n\
                              command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t /usr/share/icons/hicolor || :"))
        .post_uninstall_script(sh("command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q /usr/share/applications || :"));

    let (mut files, mut dirs) = (Vec::new(), Vec::new());
    walk(stage, stage, &mut files, &mut dirs);
    for d in &dirs {
        let dest = format!("/{}", d.strip_prefix(stage)?.to_string_lossy());
        if OWNED_DIRS.iter().any(|o| dest == *o || dest.starts_with(&format!("{o}/"))) {
            b = b.with_file(&empty, FileOptions::new(dest).mode(FileMode::dir(0o755)))?;
        }
    }
    for f in &files {
        let dest = format!("/{}", f.strip_prefix(stage)?.to_string_lossy());
        let mode = if dest == "/usr/bin/gagyebu" { 0o755 } else { 0o644 };
        let mut opt = FileOptions::new(dest.clone()).mode(FileMode::regular(mode));
        if dest.starts_with("/usr/share/doc/") {
            opt = opt.is_doc();
        }
        b = b.with_file(f, opt)?;
    }
    let pkg = b.build()?;
    pkg.write_file(out)?;
    println!("만듦: {} (파일 {}개, 소유 폴더 {}개)", out.display(), files.len(),
             dirs.iter().filter(|d| { let s = format!("/{}", d.strip_prefix(stage).unwrap().to_string_lossy());
                                      OWNED_DIRS.iter().any(|o| s == *o || s.starts_with(&format!("{o}/"))) }).count());
    Ok(())
}

fn show(path: &Path) -> Result<(), Box<dyn std::error::Error>> {
    let p = rpm::Package::open(path)?;
    let m = &p.metadata;
    println!("이름: {}  버전: {}-{}  아키텍처: {}", m.get_name()?, m.get_version()?, m.get_release()?, m.get_arch()?);
    println!("요약: {}", m.get_summary()?);
    println!("Requires: {:?}", m.get_requires()?.iter().map(|d| d.name.clone()).filter(|n| !n.starts_with("rpmlib(")).collect::<Vec<_>>());
    println!("Recommends: {:?}", m.get_recommends()?.iter().map(|d| d.name.clone()).collect::<Vec<_>>());
    println!("%preun: {:?}", m.get_pre_uninstall_script().map(|s| s.script).ok());
    for f in m.get_file_entries()? {
        println!("  {:?} {:o} {}:{} {:>6}  {}", f.mode, f.mode.permissions(), f.ownership.user, f.ownership.group,
                 f.size, f.path.display());
    }
    Ok(())
}

fn main() {
    let a: Vec<String> = std::env::args().collect();
    let r = match a.get(1).map(String::as_str) {
        Some("build") if a.len() == 5 => build(Path::new(&a[2]), &a[3], Path::new(&a[4])),
        Some("show") if a.len() == 3 => show(Path::new(&a[2])),
        _ => {
            eprintln!("사용법: rpm-builder build <stage> <버전> <출력.rpm> | rpm-builder show <파일.rpm>");
            std::process::exit(2);
        }
    };
    if let Err(e) = r {
        eprintln!("오류: {e}");
        std::process::exit(1);
    }
}
