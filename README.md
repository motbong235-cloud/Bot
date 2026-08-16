# Kairozen Referral Bot

## មុខងារ
- ណែនាំមិត្ត 1 នាក់ = $0.20 (កំណត់បានតាម `REFERRAL_BONUS`)
- ដកលុយអប្បបរមា $2.50 (កំណត់បានតាម `MIN_WITHDRAW`)
- តម្រូវឲ្យចូល Channel មុនទទួលបានប្រាក់ណែនាំ (force-subscribe gate) — **គ្មានការតម្រូវលេខទូរស័ព្ទទេ** អត្តសញ្ញាណកំណត់ដោយ Telegram user ID
- ប្រាក់ណែនាំចេញភ្លាមៗពេលចូល Channel ប៉ុន្តែស្ថិតក្នុង Grace Period រហូតដល់ត្រូវបានផ្ទៀងផ្ទាត់
- Admin Panel: ស្ថិតិ, សំណើដកលុយ (អនុម័ត/បដិសេធ), ផ្សព្វផ្សាយសារ, កំណត់ Channel, កែសមតុល្យ User, បញ្ជីណែនាំដែលត្រូវបានដកវិញ

## ការការពារការក្លែងបន្លំ (Anti-Fraud)
1. **គណនីរបស់ខ្លួនឯង** — Bot បដិសេធស្វ័យប្រវត្តិបើអ្នកចុចលីងណែនាំរបស់ខ្លួនឯង
2. **ប្រាក់ណែនាំចេញតែម្តង** — `finalize_referral()` idempotent៖ ចេញលុយតែពេលចូល Channel ហើយ `referred_by` នៅទទេប៉ុណ្ណោះ
3. **ត្រួតពិនិត្យបន្តបន្ទាប់ (Grace Period)** — ប្រាក់ណែនាំចេញភ្លាមៗ ប៉ុន្តែជា "pending" រយៈពេល `REFERRAL_GRACE_HOURS` (default 24ម៉ោង); background watchdog (`referral_watchdog()`) នឹង recheck membership ក្រោយផុតកំណត់ — បើមិត្តភ័ក្តិនៅតែក្នុង Channel ប្រាក់ក្លាយជាស្ថាពរ, បើចាកចេញ ប្រាក់ត្រូវបានដកវិញពីអ្នកណែនាំ (claw-back) ស្វ័យប្រវត្តិ
4. **កំណត់ត្រាសវនកម្ម (audit log)** — គ្រប់ព្រឹត្តិការណ៍ credit/revert ត្រូវបានកត់ត្រានៅ `referral_log.json` ដើម្បីតាមដានក្រោយ
5. **សមតុល្យមិនអាចអវិជ្ជមាន** — Admin កែសមតុល្យ ឬ claw-back មិនឲ្យចុះក្រោម $0
6. **Admin Panel > ↩️ ណែនាំដែលត្រូវបានដកវិញ** — មើលបញ្ជីករណីដែលអ្នកត្រូវបានណែនាំចាកចេញ Channel មុនផុត grace period

## ការដំឡើង (local)
```
pip install -r requirements.txt
export BOT_TOKEN="xxxxx:yyyyy"
export ADMIN_IDS="8266854899"
export CHANNEL_USERNAME="@your_channel"
python bot.py
```

## ដំឡើងលើ Render
1. Push ទៅ GitHub repo
2. Render > New Web Service > ភ្ជាប់ repo (មាន `render.yaml` រួចរាល់)
3. កំណត់ Environment Variable `BOT_TOKEN` ជា Secret
4. Deploy — Render នឹងប្រើ Flask keep-alive route `/` ស្វ័យប្រវត្តិ

## សំខាន់
- Bot ត្រូវតែជា **Admin** នៅក្នុង Channel ដែលកំណត់ (`CHANNEL_USERNAME` ឬតាម `/admin` > ⚙️ កំណត់ Channel) ដើម្បីឲ្យ `get_chat_member` ដំណើរការ។
- `DATA_DIR` គួរតែ point ទៅ Render Persistent Disk ដើម្បីកុំឲ្យទិន្នន័យបាត់ពេល redeploy។
- ប្រាក់ណែនាំគិតតែម្តងគត់ក្នុងមួយ user (ពេលចូល Channel ជោគជ័យលើកដំបូង) ដើម្បីការពារ double-credit។
- សំណើដកលុយកាត់សមតុល្យភ្លាមៗ ហើយសង​ត្រលប់វិញប្រសិនបើ Admin បដិសេធ។

## Admin Commands
- `/admin` — បើក Admin Panel (inline buttons)
