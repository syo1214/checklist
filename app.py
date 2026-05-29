from flask import Flask, render_template, request, jsonify
import requests
from bs4 import BeautifulSoup
import re

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False  # 顔文字・日本語をそのままJSONで返す

def clean_girl_name(raw):
    """タイトル文字列から本名部分だけを抽出する。
    例: '希咲那奈心弾む清楚AV女優さんのプロフィール' → '希咲那奈'
        '足立えみりさん' → '足立えみり'
    """
    if not raw:
        return raw
    # 末尾サフィックスを除去
    raw = re.sub(r'さんのプロフィール.*$', '', raw)
    raw = re.sub(r'さん$', '', raw)
    raw = re.sub(r'ちゃん.*$', '', raw)
    raw = re.sub(r'のプロフィール.*$', '', raw)
    raw = re.sub(r'（[^）]+）', '', raw)   # （〇歳）など
    raw = raw.strip()
    # ASCIIが出てきたらそこで打ち切り（AV女優、S級 など）
    raw = re.sub(r'[A-Za-z].+$', '', raw).strip()
    # ハートや記号が出てきたらそこで打ち切り
    raw = re.sub(r'[♥♡★☆◆◇●○■□▲△▼▽♦♣♠♪♫♬！!].+$', '', raw).strip()
    if not raw:
        return raw
    # 名前パターン: 漢字1〜4文字 + ひらがな/カタカナ0〜5文字
    m = re.match(r'^([一-龥]{1,4}[ぁ-んァ-ヶー]{0,5})', raw)
    if m:
        result = m.group(1).strip()
        # 末尾が動詞の活用語尾（む/く/ぐ）なら漢字を含みすぎ → 2文字以内で再試行
        if result and result[-1] in 'むくぐ':
            m2 = re.match(r'^([一-龥]{1,2}[ぁ-んァ-ヶー]{0,5})', raw)
            if m2 and len(m2.group(1)) >= 2:
                return m2.group(1).strip()
        return result
    # 純ひらがな/カタカナ名
    m = re.match(r'^([ぁ-んァ-ヶー]{2,8})', raw)
    if m:
        return m.group(0)
    return raw[:8].strip()

def scrape_diary(base_url, headers):
    """写メ日記を取得して性格・プレイ傾向を分析"""
    result = {'titles': [], 'latest_body': '', 'personality': [], 'play_hints': []}
    try:
        diary_url = base_url.rstrip('/') + '/syame/'
        resp = requests.get(diary_url, headers=headers, timeout=8)
        resp.encoding = 'utf-8'
        soup = BeautifulSoup(resp.text, 'html.parser')

        # 日記リンクとタイトルを取得
        diary_links = []
        for a in soup.select('a[href*="/syame-"]'):
            href = a.get('href', '')
            # タイトルのみ抽出（日付・数字を除去）
            raw = a.get_text(strip=True)
            title = re.sub(r'\d{4}/\d{2}/\d{2}.*', '', raw).strip()
            title = re.sub(r'\d+$', '', title).strip()
            if href and title:
                full_url = 'https://fuzokudx.com' + href if href.startswith('/') else href
                diary_links.append({'url': full_url, 'title': title})

        # 重複除去して上位5件
        seen = set()
        unique_links = []
        for d in diary_links:
            if d['title'] not in seen:
                seen.add(d['title'])
                unique_links.append(d)
        diary_links = unique_links
        result['titles'] = [d['title'] for d in diary_links[:5]]

        # 最新2件の本文を取得
        bodies = []
        for entry in diary_links[:2]:
            try:
                er = requests.get(entry['url'], headers=headers, timeout=6)
                er.encoding = 'utf-8'
                es = BeautifulSoup(er.text, 'html.parser')
                # 本文テキストを抽出（ナビ・ヘッダを除いた本文部分）
                for tag in es.select('nav, header, footer, script, style'):
                    tag.decompose()
                body = es.get_text(separator=' ', strip=True)
                # 長すぎる場合は先頭400文字
                bodies.append(body[:400])
            except Exception:
                pass
        result['latest_body'] = ' '.join(bodies)

        # 全テキストから性格・プレイ傾向を分析
        all_text = ' '.join(result['titles']) + ' ' + result['latest_body']

        personality_rules = [
            ('甘え・イチャイチャ系',   ['イチャイチャ', 'いちゃいちゃ', '甘え', 'ラブラブ', 'くっつき', '甘い']),
            ('積極的・エロ好き',        ['エロ', 'えろ', '積極', 'ガツガツ', 'エッチ', 'えっち', 'スケベ']),
            ('フレンドリー・話し好き',  ['話', 'トーク', 'おしゃべり', '楽しく', '笑', '雑談']),
            ('サービス精神旺盛',        ['サービス', 'ホスピタリティ', '気遣い', '喜ばせ', '満足']),
            ('ドS・リード系',           ['S', 'ドS', 'リード', '意地悪', '命令', '支配']),
            ('癒し・おっとり系',        ['癒し', 'ほんわか', 'やさし', '穏やか', 'まったり', 'のんびり']),
        ]
        for label, kws in personality_rules:
            if any(kw in all_text for kw in kws):
                result['personality'].append(label)

        play_rules = [
            ('イチャイチャ・密着プレイが好き', ['イチャイチャ', 'くっつき', '密着', 'ハグ']),
            ('フェラ・口サービス得意',          ['フェラ', 'チク', 'お口', '舐め', '口で']),
            ('騎乗位・主導権を取る',            ['騎乗', '上に', 'リード', '動く']),
            ('会話・コミュニケーション重視',    ['話', 'トーク', '会話', 'おしゃべり']),
        ]
        for label, kws in play_rules:
            if any(kw in all_text for kw in kws):
                result['play_hints'].append(label)

    except Exception:
        pass
    return result


def analyze_appearance(pr_text):
    """店舗PRテキストから顔の系統・外見傾向を判定"""
    face_rules = [
        ('モデル系',     ['モデル', 'スレンダー', '長身', '高身長', 'すらっ', 'スタイル抜群']),
        ('清楚系',       ['清楚', 'おっとり', '上品', '品', '落ち着', '知的']),
        ('可愛い系',     ['可愛い', 'キュート', 'ロリ', '童顔', 'ほわ', '小動物']),
        ('ギャル系',     ['ギャル', '派手', 'ノリ', '元気', '活発']),
        ('色気・妖艶系', ['色気', '妖艶', '艶', 'セクシー', 'フェロモン', '大人の魅力']),
        ('癒し系',       ['癒し', 'ほんわか', 'やさし', '穏やか', 'ふんわり']),
        ('お姉さん系',   ['お姉さん', '大人っぽ', '熟女', '人妻', '既婚']),
    ]
    result = []
    for label, kws in face_rules:
        if any(kw in pr_text for kw in kws):
            result.append(label)
    return result if result else ['情報不足']


# 主要ホテルチェーンの知識ベース（スクレイピング不要）
HOTEL_CHAIN_DB = {
    'apahotel.com': {
        'name_prefix': 'アパホテル',
        'features': ['WiFi'],
        'notes': ['ビジネスホテル標準、清潔感◎', 'APA独自の固めのマットレス', 'コンパクトな造り', '室内冷蔵庫・TV完備'],
    },
    'toyoko-inn.com': {
        'name_prefix': '東横INN',
        'features': ['WiFi', '朝食'],
        'notes': ['全国チェーン・清潔感◎', '朝食無料（和定食）', 'シングルはコンパクト'],
    },
    'dormy-hotels.com': {
        'name_prefix': 'ドーミーイン',
        'features': ['大浴場', 'サウナ', 'WiFi', '朝食'],
        'notes': ['大浴場・サウナが特徴（夜通し利用可）', '朝食ビュッフェ（有料）', '部屋は標準〜やや広め'],
    },
    'route-inn.co.jp': {
        'name_prefix': 'ルートイン',
        'features': ['大浴場', 'WiFi', '朝食'],
        'notes': ['大浴場あり', '朝食無料', 'ビジネスホテル標準'],
    },
    'comforttokyo.com': {
        'name_prefix': 'コンフォートホテル',
        'features': ['WiFi', '朝食'],
        'notes': ['朝食無料', '清潔感◎', 'コンパクト'],
    },
    'sotetsu-hotels.com': {
        'name_prefix': '相鉄フレッサイン',
        'features': ['WiFi'],
        'notes': ['都市型ビジネスホテル', '清潔感◎'],
    },
    'mystays.com': {
        'name_prefix': 'マイステイズ',
        'features': ['WiFi'],
        'notes': ['コンパクト設計', 'エリア多数'],
    },
}

def detect_chain(url):
    """URLからホテルチェーンを判定"""
    for domain, info in HOTEL_CHAIN_DB.items():
        if domain in url:
            return info
    return None


def scrape_hotel_page(url, room_number=''):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Upgrade-Insecure-Requests': '1',
    }
    result = {'name': '', 'access': '', 'features': [], 'room_type': '', 'reader_notes': []}

    # ① チェーン知識ベースで即座に判定（スクレイピング不要）
    chain_info = detect_chain(url)
    if chain_info:
        result['features'] = chain_info.get('features', [])
        result['chain_notes'] = chain_info.get('notes', [])
        result['name_prefix'] = chain_info.get('name_prefix', '')

    # URLスラッグからホテル名のヒントを取得
    # 例: /hotel/shutoken/13-tokyo/gotanda/ → "五反田" エリア
    slug_area = ''
    area_map = {
        'gotanda': '五反田', 'shinjuku': '新宿', 'ikebukuro': '池袋',
        'shibuya': '渋谷', 'akihabara': '秋葉原', 'ueno': '上野',
        'asakusa': '浅草', 'shinagawa': '品川', 'ginza': '銀座',
        'yokohama': '横浜', 'osaka': '大阪', 'nagoya': '名古屋',
        'sapporo': '札幌', 'fukuoka': '福岡',
    }
    for slug, area in area_map.items():
        if slug in url.lower():
            slug_area = area
            break

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = 'utf-8'
        soup = BeautifulSoup(resp.text, 'html.parser')
        full_text = soup.get_text(separator=' ')

        # ホテル名（meta優先 → h1フォールバック）
        og_title = soup.find('meta', property='og:title')
        title_tag = soup.find('title')
        for src in [
            og_title.get('content', '') if og_title else '',
            title_tag.get_text(strip=True) if title_tag else '',
        ]:
            if src:
                t = re.sub(r'[｜|丨/].*$', '', src).strip()
                t = re.sub(r'(【.+?】|公式|ホームページ|オフィシャルサイト|じゃらん|楽天トラベル|Hotels\.com)', '', t).strip()
                t = re.sub(r'\s+', ' ', t).strip()
                if t and t not in ('404', '403', 'Access Denied', 'Not Found', 'Error'):
                    result['name'] = t[:60]
                    break
        if not result['name']:
            h1 = soup.select_one('h1')
            if h1:
                result['name'] = h1.get_text(strip=True)[:60]

        # metaのdescriptionからも情報を拾う
        meta_desc = ''
        for el in soup.select('meta[name="description"], meta[property="og:description"]'):
            c = el.get('content', '')
            if len(c) > 20:
                meta_desc = c
                break

        # アクセス（駅徒歩） — full_text + meta_desc を対象
        search_text = full_text + ' ' + meta_desc
        access_patterns = [
            r'([^\s。\n]{2,10}駅[^\s。\n]{0,15}(?:徒歩|約)\d+分)',
            r'([^\s。\n]{2,10}駅[^\s。\n]{0,10}\d+分)',
            r'(徒歩\d+分[^\s。\n]{0,20})',
        ]
        for pat in access_patterns:
            m = re.search(pat, search_text)
            if m:
                result['access'] = m.group(1).strip()
                break

        # 階数の推定（部屋番号から）
        floor = None
        room_str = str(room_number).strip()
        if room_str:
            fm = re.match(r'^(\d{1,2})\d{2}$', room_str)
            if fm:
                floor = int(fm.group(1))
                result['floor'] = floor

        # 部屋タイプ検索（ページ内に部屋番号またはキーワードがあれば）
        room_type_kws = ['シングル', 'ダブル', 'ツイン', 'スイート', 'セミダブル', 'デラックス',
                         'スタンダード', 'プレミアム', 'ユニバーサル', 'バリアフリー']
        if room_str:
            # 部屋番号周辺テキスト
            ctx = re.findall(rf'.{{0,80}}{re.escape(room_str)}.{{0,80}}', full_text)
            if ctx:
                result['room_context'] = ctx[0].strip()[:200]
                # そのコンテキスト内で部屋タイプを探す
                for kw in room_type_kws:
                    if kw in ctx[0]:
                        result['room_type'] = kw
                        break

        # 部屋タイプが取れなければページ全体から多数決
        if not result['room_type']:
            counts = {}
            for kw in room_type_kws:
                c = full_text.count(kw)
                if c > 0:
                    counts[kw] = c
            if counts:
                result['room_type_candidates'] = sorted(counts, key=counts.get, reverse=True)[:3]

        # アメニティ・設備
        amenity_map = [
            ('大浴場',   ['大浴場']),
            ('温泉',     ['温泉', '天然温泉']),
            ('サウナ',   ['サウナ']),
            ('コンビニ', ['コンビニ', 'セブン', 'ローソン', 'ファミマ', 'ミニストップ']),
            ('朝食',     ['朝食', 'バイキング', 'ブッフェ']),
            ('駐車場',   ['駐車場', 'パーキング']),
            ('WiFi',     ['Wi-Fi', 'WiFi', '無線LAN', 'ネット無料']),
            ('ジム',     ['フィットネス', 'ジム', 'トレーニング']),
            ('レストラン', ['レストラン', 'ダイニング']),
        ]
        for label, kws in amenity_map:
            if any(kw in full_text for kw in kws):
                result['features'].append(label)

        # ベッドサイズ（記事で使える情報）
        bed_m = re.search(r'(\d{3,4})\s*[×x×]\s*(\d{3,4})', full_text)
        if bed_m:
            result['bed_size'] = f"{bed_m.group(1)}×{bed_m.group(2)}cm"

        # 読者が気にしそうなポイントを生成（スクレイピング成功時）
        _build_reader_notes(result, floor)

    except Exception as e:
        result['error'] = str(e)

    # スクレイピング失敗 or チェーン判定だけの場合でも notes を生成
    if not result.get('reader_notes'):
        _build_reader_notes(result, floor if 'floor' in result else None)

    # ホテル名の補完（チェーン + エリア）
    bad_names = {'', '404', '403', 'Access Denied', 'Not Found', 'Error', 'Forbidden'}
    if result.get('name', '') in bad_names and result.get('name_prefix'):
        result['name'] = result['name_prefix'] + (f' {slug_area}' if slug_area else '')

    return result


def _build_reader_notes(result, floor):
    notes = []
    if result.get('access'):
        notes.append(f'📍 {result["access"]}')
    if floor is not None:
        if floor >= 15:
            notes.append(f'🏙️ {floor}階 — 高層、眺望◎・夜景あり')
        elif floor >= 8:
            notes.append(f'🌆 {floor}階 — 中高層、程よい眺め')
        elif floor >= 4:
            notes.append(f'🏢 {floor}階 — 標準的な階層')
        else:
            notes.append(f'🏠 {floor}階 — 低層（外の音・明るさに注意）')
    if result.get('room_type'):
        notes.append(f'🛏️ 部屋タイプ: {result["room_type"]}')
    elif result.get('room_type_candidates'):
        notes.append(f'🛏️ 部屋タイプ候補: {" / ".join(result["room_type_candidates"])}（要確認）')
    if result.get('bed_size'):
        notes.append(f'🛏️ ベッドサイズ: {result["bed_size"]}')
    for feat in result.get('features', []):
        if feat == '大浴場':    notes.append('♨️ 大浴場あり（取材後の入浴可）')
        elif feat == '温泉':    notes.append('♨️ 温泉あり')
        elif feat == 'サウナ':  notes.append('🧖 サウナあり')
        elif feat == 'コンビニ': notes.append('🏪 コンビニ近接 or 館内あり')
        elif feat == '朝食':    notes.append('🍳 朝食あり')
        elif feat == 'WiFi':    notes.append('📶 WiFi完備')
    # チェーン固有のメモ
    for n in result.get('chain_notes', []):
        notes.append(f'ℹ️ {n}')
    if not notes:
        notes.append('⚠️ 詳細情報は手動で補足してください')
    result['reader_notes'] = notes


def scrape_girl_page(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        # URLが女性プロフィールかショップページかを判定
        is_girl_page = '/girllist/' in url

        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = 'utf-8'
        soup = BeautifulSoup(resp.text, 'html.parser')

        data = {'is_girl_page': is_girl_page}

        # 女性名（女性ページのみ）
        if is_girl_page:
            name_el = soup.select_one('h1.girlName, .girl-name, h1')
            if name_el:
                data['girl_name'] = name_el.get_text(strip=True)

        # ページタイトルからも試みる
        title_el = soup.find('title')
        if title_el:
            data['page_title'] = title_el.get_text(strip=True)

        # 店舗名
        shop_el = soup.select_one('.shopName, .shop-name, a[href*="/shop/"]')
        if shop_el:
            data['shop_name'] = shop_el.get_text(strip=True)

        # パンくずリストから情報取得
        breadcrumbs = soup.select('.breadcrumb li, .breadcrumbs li, nav li')
        if breadcrumbs:
            data['breadcrumbs'] = [b.get_text(strip=True) for b in breadcrumbs]

        # プロフィールテーブルから取得
        profile_data = {}
        rows = soup.select('table tr, .profile-item, dl dt, dl dd')

        # dtとddのペアを取得
        dts = soup.select('dl dt')
        dds = soup.select('dl dd')
        for dt, dd in zip(dts, dds):
            key = dt.get_text(strip=True)
            val = dd.get_text(strip=True)
            profile_data[key] = val

        # テーブル行から取得
        for row in soup.select('table tr'):
            cells = row.select('th, td')
            if len(cells) >= 2:
                key = cells[0].get_text(strip=True)
                val = cells[1].get_text(strip=True)
                profile_data[key] = val

        data['profile'] = profile_data

        # URLからエリア・業態・店舗スラッグを推測
        # 例: /kanto/shop/gotandahitoduma/girllist/773248/
        url_parts = url.rstrip('/').split('/')
        if 'shop' in url_parts:
            shop_idx = url_parts.index('shop')
            if shop_idx + 1 < len(url_parts):
                data['shop_slug'] = url_parts[shop_idx + 1]

        # h1から女性名だけ抽出（女性ページのみ）
        if is_girl_page:
            raw_girl = data.get('girl_name', '')
            if raw_girl:
                data['girl_name_clean'] = clean_girl_name(raw_girl)

        # テキスト全体からキーワードを探す
        full_text = soup.get_text()

        # 年齢・身長・スリーサイズ（女性ページのみ）
        if is_girl_page:
            age_paren = re.search(r'\((\d{2})\)', full_text)
            age_kanji = re.search(r'(\d{2})歳', full_text)
            if age_paren:
                data['age'] = age_paren.group(1) + '歳'
            elif age_kanji:
                data['age'] = age_kanji.group(0)

            tbwh = re.search(r'T[:\s]*(\d{2,3})\s+B[:\s]*(\d{2,3})\(([A-Za-z])\)\s+W[:\s]*(\d{2,3})\s+H[:\s]*(\d{2,3})', full_text)
            if tbwh:
                data['height'] = tbwh.group(1) + 'cm'
                data['size'] = f"B{tbwh.group(2)}({tbwh.group(3).upper()}) W{tbwh.group(4)} H{tbwh.group(5)}"
            else:
                height_match = re.search(r'(\d{3})cm', full_text)
                if height_match:
                    data['height'] = height_match.group(0)
                size_match = re.search(r'B(\d{2,3})\(([A-Z])\)\s*W(\d{2,3})\s*H(\d{2,3})', full_text)
                if size_match:
                    data['size'] = f"B{size_match.group(1)}({size_match.group(2)}) W{size_match.group(3)} H{size_match.group(4)}"

        # 料金（通常 + DX特割）
        prices = re.findall(r'\d{2,3}分\s*[\d,]+円', full_text)
        if prices:
            data['price'] = prices[0].strip()
            # 複数料金から最安値をDX特割として取得
            price_nums = []
            for p in prices[:10]:
                m = re.search(r'([\d,]+)円', p)
                if m:
                    price_nums.append((int(m.group(1).replace(',', '')), p.strip()))
            if price_nums:
                price_nums.sort(key=lambda x: x[0])
                cheapest = price_nums[0][1]
                if cheapest != data['price']:
                    data['price_dx'] = cheapest
        # DX特割を直接探す
        dx_match = re.search(r'DX特割[^\d]*(\d{2,3}分\s*[\d,]+円)', full_text)
        if dx_match:
            data['price_dx'] = dx_match.group(1).strip()

        # og:titleから店舗名・エリア・業態・女性名を確実に取得
        # 例: 「景子｜五反田人妻城（五反田:デリヘル/人妻）」
        og_title_el = soup.find('meta', property='og:title')
        og_title_str = og_title_el.get('content', '') if og_title_el else ''
        data['og_title'] = og_title_str
        og_m = re.search(r'[｜|](.+?)（(.+?)[：:]\s*(.+?)）', og_title_str)
        if og_m:
            data.setdefault('parsed_shop', og_m.group(1).strip())
            data.setdefault('parsed_area', og_m.group(2).strip())
            data.setdefault('parsed_genre', og_m.group(3).strip())
        # 女性名：og:titleの最初のトークン（｜の前）をクリーニングして取得
        # キャッチコピー部分も別途保存（例: 「心弾む清楚AV女優」「現役AV女優」）
        if is_girl_page and og_title_str:
            girl_name_from_og = re.match(r'^(.+?)[｜|]', og_title_str)
            if girl_name_from_og:
                raw_token = girl_name_from_og.group(1).strip()
                name_candidate = clean_girl_name(raw_token)
                if name_candidate:
                    data.setdefault('parsed_girl', name_candidate)
                    # キャッチコピー = 元トークンからさん/プロフィール等を除いた後、名前部分を除去した残り
                    catch = re.sub(r'さん(のプロフィール.*)?$', '', raw_token)
                    catch = re.sub(r'のプロフィール.*$', '', catch)
                    catch = re.sub(r'（[^）]+）', '', catch).strip()
                    catch = re.sub(r'^' + re.escape(name_candidate), '', catch).strip()
                    catch = re.sub(r'^[^ぁ-んァ-ヶー一-龥a-zA-Z]', '', catch).strip()  # 先頭の記号除去
                    if catch and len(catch) >= 3:
                        data['girl_catch'] = catch  # 例: 「心弾む清楚AV女優」「現役グラドル」

        # ページタイトルから店舗名フォールバック
        # 例: 「足立えみりさん（全裸の極み...）｜風俗DX」
        page_title_str = data.get('page_title', '')
        pt_m = re.search(r'さん（(.+?)）', page_title_str)
        if pt_m:
            data.setdefault('parsed_shop', pt_m.group(1).strip())

        # h1, h2からお店情報
        headings = [h.get_text(strip=True) for h in soup.select('h1, h2, h3')]
        data['headings'] = headings[:10]

        # 見出しから「店舗名」女性名【エリア:業態】パターンを解析
        for h in headings:
            m = re.search(r'「(.+?)」(.+?)【\s*(.+?)[：:]\s*(.+?)\s*】', h)
            if m:
                data['parsed_shop'] = m.group(1).strip()
                data['parsed_girl'] = clean_girl_name(m.group(2).strip())
                data['parsed_area'] = m.group(3).strip()
                data['parsed_genre'] = m.group(4).strip()
                break

        # 女性のPRコメントを取得（この女性専用テキストに限定）
        # 優先度1: プロフィール専用セレクタ
        pr_text_found = None
        profile_selectors = [
            '.girlDetail', '.girl-pr', '.girl-comment', '.profile-pr',
            '.pr-comment', '.catch-copy', '.girl-profile-text',
            '.profile-catch', '.girl-intro', '.girlIntro',
        ]
        for sel in profile_selectors:
            el = soup.select_one(sel)
            if el:
                t = el.get_text(strip=True)
                if len(t) > 30:
                    pr_text_found = t
                    break

        # 優先度2: mainタグ内の最初の適切な段落
        if not pr_text_found:
            main_area = soup.select_one('main, #main, .main, article, .content, #content')
            search_scope = main_area if main_area else None
            if search_scope:
                for p in search_scope.select('p'):
                    t = p.get_text(strip=True)
                    # 30〜300文字で、PR的キーワードを含む段落に限定
                    if 30 < len(t) < 300 and any(kw in t for kw in ['系', '雰囲気', '魅力', 'スタイル', '人柄', '笑顔', '可愛']):
                        pr_text_found = t
                        break

        if pr_text_found:
            data['pr_text'] = pr_text_found
            data['face_type'] = analyze_appearance(pr_text_found)
        else:
            # 取得できなかった場合は空（誤った情報より空の方が良い）
            data['face_type'] = []

        # 在籍数
        girl_count_m = re.search(r'(\d+)\s*名(?:在籍|の女の子|が在籍)', full_text)
        if girl_count_m:
            data['girl_count'] = girl_count_m.group(1)

        # 写メ日記を取得・分析
        diary = scrape_diary(url, headers)
        data['diary'] = diary

        return data

    except Exception as e:
        return {'error': str(e)}


def build_prompt(form):
    shop_name = form.get('shop_name', '')
    area = form.get('area', '')
    genre = form.get('genre', '')
    girl_name = form.get('girl_name', '')
    age = form.get('age', '')
    height = form.get('height', '')
    size = form.get('size', '')
    price = form.get('price', '')
    price_dx = form.get('price_dx', '')
    hotel_name = form.get('hotel_name', '')
    hotel_memo = form.get('hotel_memo', '')
    play_notes = form.get('play_notes', '')

    ratings = {
        '見た目':    {'stars': form.get('stars_looks', '4'),    'comment': form.get('comment_looks', '')},
        'テクニック': {'stars': form.get('stars_tech', '4'),     'comment': form.get('comment_tech', '')},
        '接客':     {'stars': form.get('stars_service', '4'),   'comment': form.get('comment_service', '')},
        'エロさ':   {'stars': form.get('stars_ero', '4'),       'comment': form.get('comment_ero', '')},
    }

    stars_text = '\n'.join([
        f"・{k}：{'★' * int(v['stars'])}{'☆' * (5 - int(v['stars']))}（{v['stars']}/5）\n  {v['comment']}"
        for k, v in ratings.items()
    ])

    title = f"「{shop_name}」{girl_name}【{area}：{genre}】"

    # 取材メモからシャワーの有無を推測
    has_shower = any(kw in play_notes for kw in ['シャワー', '洗', 'お湯', '一緒に入'])
    # 業態から攻守交代セクションを使うか判断
    is_m_kanshou = any(kw in genre for kw in ['M性感', '痴女', 'M系', 'M専'])

    # セクション構成を業態で切り替え
    if is_m_kanshou:
        main_sections = """【攻め】（500〜700文字）
・女の子がリードして攻めてくる序盤〜中盤の詳細な描写
・焦らし・手技・口技などの具体的な描写（部位・感触・リズムまで）
・こちらの反応・高まり・心の声を豊富に交えて

【攻守交代】（400〜600文字）
・攻守が入れ替わるタイミングの詳細な描写
・体位・体勢の変化を具体的に
・女性の反応の変化・声・表情・息づかい"""
    else:
        main_sections = """【メインプレイ】（600〜900文字）
・プレイのメインシーン（体位・体勢の変化を複数含めて詳細に）
・女性の反応・声・動き・表情・息づかいの描写
・こちらの感触・高まり・心の声を豊富に交えて
・クライマックスに向けた盛り上がりの流れ"""

    shower_section = '【シャワー】（150〜250文字）\n・シャワー中の会話・雰囲気・ドキッとした瞬間まで書く' if has_shower else ''

    prompt = f"""あなたは風俗体験ブログのプロライターです。
以下の情報をもとに、体験レポート記事のプレイ本文パートのみを書いてください。

---
【タイトル】
{title}

【店舗情報】
店舗名：{shop_name}
エリア：{area}
業態：{genre}
料金：{price}{f' / DX特割：{price_dx}' if price_dx else ''}
{f'ホテル：{hotel_name}' if hotel_name else ''}{f'''
ホテルメモ：{hotel_memo}''' if hotel_memo else ''}

【女性プロフィール】
名前：{girl_name}
年齢：{age}
身長：{height}
スリーサイズ：{size}

【取材メモ（音声文字起こし）】
{play_notes}

【評価コメント（参考）】
{stars_text}

---
【出力する範囲】
プレイ本文のみ。冒頭の雑談・お店紹介・女性紹介・総評・評価まとめは不要。

---
【必須セクション構成】
以下のセクションを【】見出し付きで、すべて必ず書くこと。
取材メモに情報が薄い部分は雰囲気・業態から補完・想像して書いてよいが、セクションは絶対に省略しないこと。
各セクションは指定文字数の上限に近い分量で、しっかり書き込むこと。

【女の子到着】（250〜350文字）
・ドアが開いた瞬間の第一印象・外見の詳細な描写
・プロフィール写真との比較・期待値との差
・部屋に入ってからの最初のやりとり・ドキッとした瞬間

{shower_section}

【ベッドへ】（350〜500文字）
・プレイ開始までの流れを丁寧に
・雰囲気づくり・緊張とほぐれの描写
・前戯の具体的な描写（何をされたか・どう感じたか）

{main_sections}

【フィニッシュ】（250〜350文字）
・クライマックスに至る直前の高まりの描写
・フィニッシュの瞬間と余韻
・脱力感・達成感など

【アフター】（150〜200文字）
・プレイ後の会話・女の子の素の表情
・帰り際の一言・余韻とともに終わる締め

---
【文体の指示】
- 一人称は使わず、体験談として描写中心で書く
- 語尾は「です・ます調」で統一すること（「だ・である調」や体言止めで終わらせない）
- 読者を引き込む、親しみやすく軽快な文体
- 適度に改行して読みやすく（3〜4行ごとに改行）
- 強調したいキーワードは **テキスト** で囲む（例：**長身美人**）
- 著者の心の声は（テキスト）で囲む（例：（やばい…！））
- 女性のセリフは「　」で囲む
- プレーンテキストで出力すること（HTMLタグ不要）
- 各【セクション見出し】の後は必ず本文を書くこと。見出しだけで終わらないこと。
- 全セクション合計で**2500文字以上**になるよう、各セクションを丁寧かつ濃密に書くこと。

---
【重要：情報の使用ルール】
- 今回の【取材メモ】に書かれている情報だけを使うこと。
- 過去の取材・他の女性の情報は一切使用しないこと。
- 取材メモにない情報（感度・反応・具体的な言動）は勝手に補完せず、業態・雰囲気から控えめに想像する程度にとどめること。
"""
    return prompt.strip()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/checklist')
def checklist():
    import os
    path = os.path.join(os.path.dirname(__file__), 'checklist.html')
    with open(path, encoding='utf-8') as f:
        return f.read()


@app.route('/hotel_scrape', methods=['POST'])
def hotel_scrape():
    data = request.json or {}
    url = data.get('url', '')
    room = data.get('room', '')
    if not url:
        return jsonify({'error': 'URLを入力してください'})
    result = scrape_hotel_page(url, room)
    return jsonify(result)


@app.route('/scrape', methods=['POST'])
def scrape():
    url = request.json.get('url', '')
    if not url:
        return jsonify({'error': 'URLを入力してください'})
    data = scrape_girl_page(url)
    return jsonify(data)


@app.route('/generate', methods=['POST'])
def generate():
    prompt = build_prompt(request.form)
    return jsonify({'prompt': prompt})


if __name__ == '__main__':
    app.run(debug=False, port=5001)
