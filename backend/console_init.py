# -*- coding: utf-8 -*-
"""Console 初始化命令生成器.

新上架/管理地址未配的设备 SSH 不可达, 只能 Console 线登录.
本模块按厂商生成初始化命令: 主机名 / 管理地址 / SSH 服务 / 登录账号 / LLDP / 默认网关,
完成后设备即可被平台的网络发现 (SSH+LLDP) 扫到, 形成闭环.
"""


def build_console_init(vendor: str, hostname: str, mgmt_ip: str,
                       mgmt_mask: str = "255.255.255.0", gw: str = "",
                       username: str = "netadmin", password: str = "") -> dict:
    v = (vendor or "").lower()
    hostname = (hostname or "SW-New").strip()
    mgmt_ip = (mgmt_ip or "").strip()
    pw = password or "ChangeMe@123"

    if v in ("huawei", "hp_comware"):
        # 华为 / H3C (Comware) 体系
        cmds = [
            "system-view",
            f"sysname {hostname}",
            "lldp enable",
            "vlan 10",
            " description Mgmt",
            " quit",
        ]
        cmds += (["interface Vlanif 10"] if v == "huawei" else ["interface vlan-interface10"])
        if mgmt_ip:
            cmds.append(f" ip address {mgmt_ip} {mgmt_mask}")
        cmds += [
            " quit",
            "stelnet server enable" if v == "huawei" else "ssh server enable",
            "user-interface vty 0 4",
            " authentication-mode aaa" if v == "huawei" else " authentication-mode scheme",
            " protocol inbound ssh",
            " quit",
            "aaa",
            f" local-user {username} password cipher {pw}",
        ]
        cmds.append(f" local-user {username} privilege level 15" if v == "huawei"
                    else f" local-user {username} service-type ssh")
        cmds += [
            f" local-user {username} service-type ssh" if v == "huawei"
            else f" local-user {username} privilege level 15",
            " quit",
            f"ssh user {username} authentication-type password",
            f"ssh user {username} service-type stelnet",
            "rsa local-key-pair create" if v == "huawei" else "public-key local create rsa",
        ]
        if gw:
            cmds.append(f"ip route-static 0.0.0.0 0.0.0.0 {gw}")
        cmds += ["return", "save", "y"]

    elif v in ("cisco_ios", "ruijie_os"):
        # 思科 / 锐捷体系
        cmds = [
            "configure terminal",
            f"hostname {hostname}",
            "lldp run",
            "vlan 10",
            " name Mgmt",
            " exit",
            "interface vlan 10",
        ]
        if mgmt_ip:
            cmds.append(f" ip address {mgmt_ip} {mgmt_mask}")
        cmds += [
            " no shutdown",
            " exit",
            "ip domain-name local",
            "crypto key generate rsa modulus 2048",
            f"username {username} privilege 15 secret {pw}",
        ]
        if v == "cisco_ios":
            cmds += ["aaa new-model", "aaa authentication login default local"]
        else:
            cmds += ["aaa authentication login default local"]
        cmds += [
            "line vty 0 4",
            " transport input ssh",
            " login local",
            " exit",
            "service password-encryption",
        ]
        if gw:
            cmds.append(f"ip route 0.0.0.0 0.0.0.0 {gw}")
        cmds += ["end"]
        cmds.append("write memory")

    else:
        return {"commands": [], "message": f"暂不支持该厂商的初始化模板: {vendor}"}

    return {
        "commands": cmds,
        "message": (f"Console 线登录后依次执行以下命令 (管理员地址 {mgmt_ip or '未填'}), "
                    "完成后平台即可通过 SSH+LLDP 发现该设备"),
    }
