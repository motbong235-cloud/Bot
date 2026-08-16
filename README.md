# Kairozen Referral Bot

## មុខងារ
- ណែនាំមិត្ត 1 នាក់ = $0.20 (កំណត់បានតាម `REFERRAL_BONUS`)
- ដកលុយអប្បបរមា $2.50 (កំណត់បានតាម `MIN_WITHDRAW`)
- តម្រូវឲ្យចូល Channel មុនទទួលបានប្រាក់ណែនាំ (force-subscribe gate)
- **ផ្ទៀងផ្ទាត់លេខទូរស័ព្ទ** មុនប្រើមុខងារ/ទទួលប្រាក់ណែនាំ (លេខទូរស័ព្ទនីមួយៗប្រើបានតែម្តង — ការពារគណនីក្លែងក្លាយច្រើនគណនី)
- ប្រាក់ណែនាំចេញឲ្យតែពេលអ្នកត្រូវបានណែនាំ **ចូល Channel ផងនិងផ្ទៀងផ្ទាត់លេខទូរស័ព្ទរួច** ទាំងពីរ (មិនចេញភ្លាមៗគ្រាន់តែចូល Channel ទេ)
- Admin Panel: ស្ថិតិ, សំណើដកលុយ (អនុម័ត/បដិសេធ), ផ្សព្វផ្សាយសារ, កំណត់ Channel, កែសមតុល្យ User, បញ្ជីគណនីសង្ស័យ

## ការការពារការក្លែងបន្លំ (Anti-Fraud)
1. **គណនីរបស់ខ្លួនឯង** — Bot បដិសេធស្វ័យប្រវត្តិបើអ្នកចុចលីងណែនាំរបស់ខ្លួនឯង
2. **ផ្ទៀងផ្ទាត់លេខទូរស័ព្ទ** — user ត្រូវចែករំលែក contact ផ្ទាល់ខ្លួន (មិនអាច forward លេខអ្នកដទៃ); ប្រព័ន្ធ verify `contact.user_id == message.from_user.id`
3. **លេខទូរស័ព្ទតែម្តងគត់** — មួយលេខទូរស័ព្ទចុះឈ្មោះបានតែម្តងក្នុងប្រព័ន្ធទាំងមូល (`phones.json`); បើប្រើលេខស្ទួន គណនីនោះនឹងត្រូវ flag ថា `flagged_duplicate_phone` និងមិនអាចទទួល/បង្កើតប្រាក់ណែនាំបានទេ ព្រមទាំង Admin ទទួលការជូនដំណឹងភ្លាមៗ
4. **ប្រាក់ណែនាំចេញតែម្តង** — `finalize_referral()` idempotent៖ ចេញលុយតែពេលគ្រប់លក្ខខណ្ឌ (Channel + Phone)ហើយ `referred_by` នៅទទេប៉ុណ្ណោះ
5. **កំណត់ត្រាសវនកម្ម (audit log)** — គ្រប់ព្រឹត្តិការណ៍ credit/duplicate-block ត្រូវបានកត់ត្រានៅ `referral_log.json` ដើម្បីតាមដានក្រោយ
6. **សមតុល្យមិនអាចអវិជ្ជមាន** — Admin កែសមតុល្យបានតែមិនឲ្យចុះក្រោម $0
7. **Admin Panel > 🚩 គណនីសង្ស័យ** — មើលបញ្ជីគណនីដែលព្យាយាមប្រើលេខទូរស័ព្ទស្ទួន

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
