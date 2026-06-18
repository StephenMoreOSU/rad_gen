from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from lxml import etree

from src.coffe.vpr import print_vpr_file_flut_hard


REPO_ROOT = Path(__file__).resolve().parents[1]


def _ckt(delay: float, sp_name: str | None = None):
    return SimpleNamespace(delay=delay, sp_name=sp_name)


def _mock_fpga():
    min_width_tran_area = 2.0
    specs = SimpleNamespace(
        Rfb=[],
        Fcin=0.15,
        Fcout=0.10,
        Fs=3,
        N=10,
        K=6,
        min_width_tran_area=min_width_tran_area,
        enable_carry_chain=True,
    )

    lut_inputs = {
        name: [
            SimpleNamespace(
                driver=_ckt(100e-12),
                not_driver=_ckt(110e-12),
                delay=idx * 10e-12,
            )
        ]
        for idx, name in enumerate("abcdefgh", start=1)
    }

    return SimpleNamespace(
        specs=specs,
        area_dict={
            "logic_cluster": 2468.0,
            "switch_mux_trans_size_L4": 12.0,
            "switch_buf_size_L4": 34.0,
            "switch_mux_trans_size_L16": 20.0,
            "switch_buf_size_L16": 52.0,
            "ipin_mux_trans_size": 8.0,
            "cb_buf_size": 10.0,
        },
        lut_inputs=lut_inputs,
        sb_muxes=[
            SimpleNamespace(
                vpr_name="L4_driver",
                delay=321e-12,
                sink_wire=SimpleNamespace(type="L4"),
            ),
            SimpleNamespace(
                vpr_name="L16_driver",
                delay=654e-12,
                sink_wire=SimpleNamespace(type="L16"),
            ),
        ],
        cb_muxes=[
            SimpleNamespace(vpr_name="ipin_cblock", delay=87e-12),
        ],
        local_muxes=[_ckt(91e-12, "local_mux")],
        local_ble_outputs=[_ckt(82e-12, "local_ble_output")],
        general_ble_outputs=[_ckt(73e-12, "general_ble_output")],
        carry_chain_inter_clusters=[_ckt(11e-12, "carry_inter")],
        carry_chain_periphs=[_ckt(22e-12, "carry_periph")],
        carry_chain_muxes=[_ckt(33e-12, "carry_mux")],
        carry_chains=[],
    )


def _find_vpr_binary() -> Path:
    candidates = []

    vpr_env = os.environ.get("VPR")
    if vpr_env:
        vpr_from_path = shutil.which(vpr_env)
        candidates.append(Path(vpr_from_path) if vpr_from_path else Path(vpr_env))

    vtr_home = os.environ.get("VTR_HOME")
    if vtr_home:
        candidates.append(Path(vtr_home) / "build" / "vpr" / "vpr")

    candidates.extend(
        [
            REPO_ROOT / "third_party" / "vtr" / "build" / "vpr" / "vpr",
            REPO_ROOT / "third_party" / "vtr" / "vpr" / "vpr",
        ]
    )

    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate

    pytest.skip("VPR binary not found")


def _delay_matrix_values(root, in_port: str) -> list[float]:
    delay_nodes = root.xpath(f"//delay_matrix[@in_port='{in_port}']")
    assert len(delay_nodes) == 1
    return [float(value) for value in delay_nodes[0].text.split()]


def _switch(root, name: str):
    switches = root.xpath(f"//switchlist/switch[@name='{name}']")
    assert len(switches) == 1
    return switches[0]


def test_print_vpr_file_flut_hard_patches_arch_and_vpr_packs(tmp_path):
    input_arch = REPO_ROOT / "arch.xml"
    blif = REPO_ROOT / "third_party" / "vtr" / "vtr_flow" / "benchmarks" / "microbenchmarks" / "and.blif"
    assert input_arch.is_file(), f"Missing VPR architecture fixture: {input_arch}"
    assert blif.is_file(), f"Missing VPR BLIF fixture: {blif}"

    patched_arch = tmp_path / "patched_arch.xml"
    lut_delays = {
        f"lut_{name}": delay
        for name, delay in zip(
            "abcdefgh",
            [101e-12, 202e-12, 303e-12, 404e-12, 505e-12, 606e-12, 707e-12, 808e-12],
        )
    }

    print_vpr_file_flut_hard(
        vpr_file=None,
        fpga_inst=_mock_fpga(),
        input_xml=str(input_arch),
        output_xml=str(patched_arch),
        delay_dict=lut_delays,
    )

    tree = etree.parse(str(patched_arch))
    root = tree.getroot()

    assert root.xpath("string(//device/area/@grid_logic_tile_area)") == "1234.0"

    l4_switch = _switch(root, "L4_driver")
    assert l4_switch.get("Tdel") == str(321e-12)
    assert l4_switch.get("mux_trans_size") == "6.0"
    assert l4_switch.get("buf_size") == "17.0"

    l16_switch = _switch(root, "L16_driver")
    assert l16_switch.get("Tdel") == str(654e-12)
    assert l16_switch.get("mux_trans_size") == "10.0"
    assert l16_switch.get("buf_size") == "26.0"

    cb_switch = _switch(root, "ipin_cblock")
    assert cb_switch.get("Tdel") == str(87e-12)
    assert cb_switch.get("mux_trans_size") == "4.0"
    assert cb_switch.get("buf_size") == "5.0"

    assert _delay_matrix_values(root, "lut4.in") == pytest.approx(
        [101e-12, 202e-12, 303e-12, 404e-12]
    )
    assert _delay_matrix_values(root, "lut5.in") == pytest.approx(
        [101e-12, 202e-12, 303e-12, 404e-12, 505e-12]
    )
    assert _delay_matrix_values(root, "lut6.in") == pytest.approx(
        [101e-12, 202e-12, 303e-12, 404e-12, 505e-12, 606e-12]
    )

    local_mux_delays = root.xpath(
        "//complete/delay_constant[contains(@in_port, 'clb.I') and contains(@out_port, '.in')]/@max"
    )
    assert local_mux_delays
    assert set(local_mux_delays) == {str(91e-12)}

    feedback_delays = root.xpath(
        "//complete/delay_constant[contains(@in_port, '.out') and contains(@out_port, '.in')]/@max"
    )
    assert feedback_delays
    assert set(feedback_delays) == {str(82e-12)}

    output_mux_delays = root.xpath("//mux[contains(@input, 'ff.Q')]/delay_constant/@max")
    assert output_mux_delays
    assert set(output_mux_delays) == {str(73e-12)}

    carry_delays = root.xpath("//direct[@name='carry_in']/delay_constant/@max")
    assert carry_delays
    assert set(carry_delays) == {str(66e-12)}

    result = subprocess.run(
        [str(_find_vpr_binary()), str(patched_arch), str(blif), "--pack"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-4000:]
