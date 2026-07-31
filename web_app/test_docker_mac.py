"""Tests for multi-architecture Docker support."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_install_apptainer_script_supports_arm64_and_amd64():
    script = (REPO_ROOT / "docker" / "install-apptainer.sh").read_text(encoding="utf-8")
    assert "amd64)" in script
    assert "arm64)" in script
    assert "ppa:apptainer/ppa" in script
    assert "apptainer_${APPTAINER_VERSION}_amd64.deb" in script
    assert "apptainer-suid_${APPTAINER_VERSION}_amd64.deb" in script
    assert "apptainer-suid" in script


def test_compose_enables_nested_apptainer_security_options():
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "privileged: true" in compose
    assert "seccomp:unconfined" in compose
    assert "apparmor:unconfined" in compose
    assert "/dev/fuse" in compose
    assert "METATOX_VERIFY_APPTAINER" in compose


def test_configure_apptainer_forces_setuid_mode():
    script = (REPO_ROOT / "docker" / "configure-apptainer.sh").read_text(encoding="utf-8")
    assert 'set_apptainer_conf "allow setuid" "yes"' in script
    assert 'set_apptainer_conf "allow user ns" "no"' in script


def test_dockerfile_uses_install_script():
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "TARGETARCH" in dockerfile
    assert "docker/install-apptainer.sh" in dockerfile
    assert "docker/configure-apptainer.sh" in dockerfile
    assert "apptainer_1.3.6_amd64.deb" not in dockerfile


def test_mac_compose_overlay_sets_amd64_platform():
    compose = (REPO_ROOT / "docker-compose.mac.yml").read_text(encoding="utf-8")
    assert "platform: linux/amd64" in compose
