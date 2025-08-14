import re
from pathlib import Path

INPUT  = "data.txt"          # ganti sesuai file
OUTPUT = "data_hasil.txt"
MAXLEN = 25

# Regex blok interface
interface_re = re.compile(
    r"(?P<header>^\s*interface[^\n]*\n)"
    r"(?P<body>(?:^(?!\s*interface).*\n?)*)",
    re.MULTILINE
)

# Regex blok pon-onu-mng
ponmng_re = re.compile(
    r"(?P<header>^\s*pon-onu-mng\s+(?P<intf>\S+).*\n)"
    r"(?P<body>(?:^(?!\s*pon-onu-mng).*\n?)*)",
    re.MULTILINE
)

# Regex name dan description
name_re = re.compile(r"^(?P<indent>\s*)name\s+(?P<name>\S+)\s*$", re.MULTILINE)
desc_re = re.compile(
    r"^(?P<dindent>\s*)description\s+ODP-[^-]+-(?P<code>\d+/\d+)\s*$",
    re.MULTILINE | re.IGNORECASE
)

# Regex user/password
pppoe_user_re = re.compile(r"(?P<prefix>\buser\s+)(?P<val>\S+)")
pppoe_pass_re = re.compile(r"(?P<prefix>\bpassword\s+)(?P<val>\S+)")

# Simpan mapping interface -> nama final
interface_to_name = {}

def build_final_name(base_name: str, code: str, maxlen: int = MAXLEN) -> str:
    if base_name.endswith("-" + code):
        base_name = base_name[:-(len(code)+1)]

    parts = base_name.split("-")
    if not parts:
        return f"JMP-{code}"

    result = [parts[0]]
    tail = parts[1:]

    def final_len(parts_):
        return len("-".join(parts_ + [code]))

    if tail:
        result.append(tail[0])

    for part in tail[1:]:
        if final_len(result + [part]) <= maxlen:
            result.append(part)
        elif final_len(result + [part[:1]]) <= maxlen:
            result.append(part[:1])
        else:
            if len(result) >= 2:
                head0, head1 = result[0], result[1]
                for cut in range(len(head1), 2, -1):
                    test = [head0, head1[:cut]] + result[2:] + [part[:1]]
                    if final_len(test) <= maxlen:
                        result = [head0, head1[:cut]] + result[2:] + [part[:1]]
                        break
                else:
                    result = [head0, head1[:3]] + result[2:] + [part[:1]]
            else:
                result.append(part[:1])

    final_name = "-".join(result + [code])

    if len(final_name) > maxlen and len(result) >= 2:
        head0, head1 = result[0], result[1]
        suffix = "-".join(result[2:] + [code])
        allowed = maxlen - (len(head0) + 1 + 1 + len(suffix))
        if allowed < 3:
            allowed = 3
        result[1] = head1[:allowed]
        final_name = "-".join(result + [code])
        if len(final_name) > maxlen and len(result) > 2:
            result = [head0, result[1]] + [p[:1] for p in result[2:]]
            final_name = "-".join(result + [code])

    return final_name

def insert_service_port_3(body: str) -> str:
    """
    Sisipkan 'service-port 3 vport 1 user-vlan 1002 vlan 1002'
    tepat di bawah setiap baris:
    'service-port 2 vport 1 user-vlan 1001 vlan 1001'
    (toleran spasi/indent/trailing space), hindari duplikasi.
    """
    lines = body.splitlines(True)  # keepends
    new_lines = []
    for i, ln in enumerate(lines):
        new_lines.append(ln)
        m = re.match(
            r"^(\s*)service-port\s+2\s+vport\s+1\s+user-vlan\s+1001\s+vlan\s+1001\s*$",
            ln
        )
        if m:
            indent = m.group(1) or ""
            next_line = lines[i+1] if i+1 < len(lines) else ""
            already = re.match(
                r"^\s*service-port\s+3\s+vport\s+1\s+user-vlan\s+1002\s+vlan\s+1002\s*$",
                next_line
            )
            if not already:
                new_lines.append(f"{indent}service-port 3 vport 1 user-vlan 1002 vlan 1002\n")
    return "".join(new_lines)

def replace_brand_in_interface(body: str) -> str:
    # Ganti semua 'GARUDAMEDIA' → 'UNNET' di blok interface
    return body.replace("GARUDAMEDIA", "UNNET")

def remap_service_port_vlans_in_interface(body: str) -> str:
    """
    Ubah:
      SP1: 1000 -> 3020
      SP2: 1001 -> 3022
      SP3: 1002 -> 100
    Toleran spasi/indent/trailing space. Hanya sentuh vport 1.
    """
    def sub_line(pattern, repl, line):
        return re.sub(pattern, repl, line)

    out = []
    for ln in body.splitlines(True):
        # service-port 1
        ln = sub_line(
            r'^(\s*service-port\s+1\s+vport\s+1\s+user-vlan\s*)1000(\s+vlan\s*)1000(\s*)$',
            r'\g<1>3020\g<2>3020\g<3>',
            ln
        )
        # service-port 2
        ln = sub_line(
            r'^(\s*service-port\s+2\s+vport\s+1\s+user-vlan\s*)1001(\s+vlan\s*)1001(\s*)$',
            r'\g<1>3022\g<2>3022\g<3>',
            ln
        )
        # service-port 3
        ln = sub_line(
            r'^(\s*service-port\s+3\s+vport\s+1\s+user-vlan\s*)1002(\s+vlan\s*)1002(\s*)$',
            r'\g<1>100\g<2>100\g<3>',
            ln
        )
        out.append(ln)
    return "".join(out)

def process_interface_block(interface_name: str, body: str) -> str:
    mname = name_re.search(body)
    mdesc = desc_re.search(body)
    if not mname or not mdesc:
        # Tetap jalankan update yang sudah kita tambahkan sebelumnya
        body = insert_service_port_3(body)
        body = replace_brand_in_interface(body)
        body = remap_service_port_vlans_in_interface(body)
        return body

    base_name = mname.group("name")
    name_indent = mname.group("indent")
    code = mdesc.group("code")

    final_name = build_final_name(base_name, code, MAXLEN)
    interface_to_name[interface_name] = final_name

    # update baris name (fungsi asli)
    body = name_re.sub(f"{name_indent}name {final_name}", body, count=1)

    # --- tambahan yang sudah terbukti bekerja, tetap dipertahankan ---
    body = insert_service_port_3(body)                 # insert 3 di bawah 2 (1001)
    body = replace_brand_in_interface(body)            # GARUDAMEDIA -> UNNET
    body = remap_service_port_vlans_in_interface(body) # 1000->3020, 1001->3022, 1002->100

    return body

def process_ponmng_block(intf_name: str, body: str) -> str:
    # fungsi asli: ganti user/pass + sisip TR069 & tr069-mgmt
    final_name = interface_to_name.get(intf_name)
    if not final_name:
        return body

    lines = body.splitlines(True)  # keepends
    new_lines = []
    last_wifi_idx = None  # catat baris terakhir vlan port wifi

    for idx, ln in enumerate(lines):
        # ganti user/password
        ln = pppoe_user_re.sub(lambda m: f"{m.group('prefix')}{final_name}", ln)
        ln = pppoe_pass_re.sub(lambda m: f"{m.group('prefix')}{final_name}", ln)
        new_lines.append(ln)

        # sisipkan service TR069 setelah HOTSPOT
        if re.search(r"service HOTSPOT", ln):
            new_lines.append(f"  service TR069 gemport 1 vlan 100\n")

        # catat baris terakhir vlan port wifi
        if re.search(r"vlan port wifi", ln):
            last_wifi_idx = len(new_lines) - 1

    # sisipkan TR069-mgmt hanya sekali setelah baris terakhir vlan port wifi
    if last_wifi_idx is not None:
        insert_lines = (
            "  tr069-mgmt 1 state unlock\n"
            "  tr069-mgmt 1 acs http://172.17.11.6:7547 validate basic username unnet.acs password unnet.acs123\n"
            "  tr069-mgmt 1 tag pri 0 vlan 100\n"
        )
        new_lines.insert(last_wifi_idx + 1, insert_lines)

    return "".join(new_lines)

def main():
    text = Path(INPUT).read_text(encoding="utf-8", errors="ignore")
    out, last = [], 0

    # proses blok interface dulu (sesuai alur asli)
    for m in interface_re.finditer(text):
        out.append(text[last:m.start()])
        header = m.group("header")
        body = m.group("body")

        intf_match = re.match(r"\s*interface\s+(\S+)", header)
        if intf_match:
            interface_name = intf_match.group(1)
            body = process_interface_block(interface_name, body)
        else:
            # fallback: tetap jalankan transformasi tambahan
            body = insert_service_port_3(body)
            body = replace_brand_in_interface(body)
            body = remap_service_port_vlans_in_interface(body)

        out.append(header)
        out.append(body)
        last = m.end()
    text_after_interface = "".join(out)

    # proses blok pon-onu-mng (sesuai alur asli)
    final_text = []
    last = 0
    for m in ponmng_re.finditer(text_after_interface):
        final_text.append(text_after_interface[last:m.start()])
        header = m.group("header")
        body = m.group("body")
        intf_name = m.group("intf")
        body = process_ponmng_block(intf_name, body)
        final_text.append(header)
        final_text.append(body)
        last = m.end()
    final_text.append(text_after_interface[last:])

    Path(OUTPUT).write_text("".join(final_text), encoding="utf-8")
    print(f"Selesai. Hasil: {OUTPUT}")

if __name__ == "__main__":
    main()
