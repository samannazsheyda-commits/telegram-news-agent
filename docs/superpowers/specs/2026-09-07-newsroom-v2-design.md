# بی‌خبر Newsroom V2 — Production Design

## هدف

V2 باید ایجنت خبری را از معماری «فچ → فیلتر → شاید انتشار» به یک نیوزروم قابل ردیابی تبدیل کند که در آن هیچ خبر مهمی بی‌صدا گم نمی‌شود، هر تصمیم قابل توضیح است و پنل مستقل از auto-publish همیشه ورودی زنده را نشان می‌دهد.

## معیارهای موفقیت

1. هیچ خبر Priority مرتبط با ایران، جنگ، امنیت، تحریم، هرمز، حملات، حریم هوایی، NOTAM، ترامپ/Truth Social، CENTCOM، کاخ سفید و مقام‌های کلیدی به دلیل شباهت موضوعی کلی حذف نشود.
2. خبر تکراری واقعی از چند منبع فقط یک رویداد باشد؛ اما تغییر عدد، تصمیم تازه، موضع رسمی تازه، تغییر وضعیت، مکان تازه یا اقدام تازه به‌عنوان رویداد/آپدیت مستقل عبور کند.
3. هر خبر دریافت‌شده یک trace داشته باشد: fetched → normalized → classified → dedup decision → publish/wait/reject.
4. پنل در حالت auto_publish=true نیز خالی نباشد و ورودی زنده‌ی امروز را نشان دهد.
5. هیچ suppression بدون reason و duplicate_of انجام نشود.
6. انتشار موفق فقط وقتی success محسوب شود که Telegram API پاسخ موفق با message_id بدهد.
7. restart یا اجرای بعدی باعث انتشار دوباره‌ی همان رویداد نشود.

## معماری کلان

### 1. Source Intake

تمام source adapters فقط وظیفه‌ی دریافت و تبدیل به `RawNewsItem` را دارند. هیچ source adapter حق تصمیم editorial یا dedup ندارد.

فیلدهای پایه:
- source
- source_url
- source_item_id
- published_at
- fetched_at
- title
- summary/body
- media
- source_priority

Source failures مستقل ثبت می‌شوند؛ شکست یک منبع نباید کل cycle را متوقف کند.

### 2. Normalization

هر RawNewsItem به `NormalizedNewsItem` تبدیل می‌شود:
- canonical actors
- canonical locations
- action verbs
- topic tags
- numeric facts
- quoted speaker
- timestamps
- media type
- language-normalized text

Normalization نباید خبر را حذف کند.

### 3. Event Fingerprint

برای هر خبر یک fingerprint ساختاری ساخته می‌شود:

`actor + action + object + location + key facts + time bucket`

شباهت متن فقط یک signal کمکی است، نه دلیل نهایی حذف.

مثال‌های مستقل:
- آمریکا می‌گوید کنترل هرمز را در دست دارد.
- ایران منطقه محدود جدید اعلام می‌کند.
- CENTCOM می‌گوید 92 کشتی تغییر مسیر داده‌اند.

مثال duplicate واقعی:
- AP/CNN/NYT همگی گزارش می‌دهند آمریکا سه نفتکش ایرانی را زده است.

### 4. Event Ledger

فایل/استور جدید `data/event_ledger.json` نگهدارنده‌ی eventهای canonical است.

هر event شامل:
- event_id
- fingerprint
- canonical_title
- first_seen
- last_updated
- primary_source
- source_variants[]
- key_facts
- published_message_ids[]
- status

اگر خبر تازه همان event باشد ولی fact تازه داشته باشد، event update می‌شود و می‌تواند دوباره به‌عنوان `material_update` منتشر شود.

### 5. Dedup Decision Engine

خروجی دقیقاً یکی از این‌هاست:
- `new_event`
- `material_update`
- `duplicate_exact`
- `duplicate_same_claim`
- `needs_editorial_review`

قواعد حفاظتی:
- Priority source statement با محتوای substantively تازه هرگز صرفاً با topic overlap حذف نمی‌شود.
- عدد تازه، action تازه، location تازه، وضعیت تازه یا speaker statement تازه default به `material_update/new_event` متمایل است.
- duplicate باید `duplicate_of=event_id` داشته باشد.
- اگر confidence برای duplicate پایین باشد، `needs_editorial_review`؛ حذف خودکار ممنوع.

### 6. Priority Guardrails

Protected classes:
- Donald Trump / Truth Social درباره ایران، هرمز، نفت، جنگ
- White House / WH spokesperson / Communications Director
- CENTCOM و CENTCOM Farsi
- State Department / Treasury when Iran-related
- Abbas Araghchi
- Mohsen Rezaei
- key Iranian military/security officials
- NOTAM / airspace closure/reopen/warning
- TankerTrackers when conflict/explosion/Hormuz traffic materially changes
- missile/drone/strike/explosion/interception events

این کلاس‌ها می‌توانند duplicate واقعی شوند، اما فقط با event match قوی، نه شباهت کلمات.

### 7. Live Panel Feed

فایل جدید `data/panel_live_feed.json` در هر cycle به‌روز می‌شود و مستقل از `editorial_queue.json` است.

هر رکورد:
- item_id
- event_id
- source
- source_url
- title
- published_at_source
- discovered_at
- decision
- decision_reason
- duplicate_of
- telegram_message_id
- panel_status

`panel_status`:
- `new`
- `auto_published`
- `waiting`
- `duplicate`
- `rejected`
- `failed`

Feed فقط خبرهای امروز/پنجره freshness را نگه می‌دارد و دارای سقف رکورد است.

### 8. Editorial Queue

`editorial_queue.json` فقط برای مواردی است که واقعاً نیاز به تصمیم انسان دارند:
- needs_editorial_review
- publication failure needing retry/review
- auto_publish=false
- emergency/quiet policy

خبر auto-published نباید دوباره pending نشان داده شود.

### 9. Publication Pipeline

ترتیب:
1. build Persian output
2. final safety/editorial validation
3. final channel/source idempotency check
4. Telegram API send
5. verify `ok=true` + `message_id`
6. update event ledger/history/live feed atomically as far as storage permits

اگر Telegram fail شود، item به `failed/waiting` می‌رود؛ seen/published نهایی نمی‌شود.

### 10. Truth Social Media Rule

هر پست ترامپ درباره ایران/هرمز/نفت:
- متن و media مستقل ingest شوند.
- اگر تصویر دارد، تصویر همراه خروجی منتشر شود.
- source Truth URL و timestamp اصلی ذخیره شود.
- هر Truth post ID یک source identity مستقل است؛ دو پست در یک دقیقه نباید صرفاً به دلیل شباهت تصویر/عنوان یکی شوند مگر exact repost باشند.

### 11. Freshness

- freshness برای publication و panel قابل تنظیم است.
- زمان اصلی source مبنا است، نه زمان fetch.
- stale content فقط برای context استفاده می‌شود و بدون material update منتشر نمی‌شود.
- today Tehran policy برای news publication حفظ می‌شود، مگر تنظیم صریح برای breaking item با timezone boundary.

### 12. Observability

هر cycle یک summary log:
- sources_ok / sources_failed
- items_fetched
- new_events
- material_updates
- exact_duplicates
- review_items
- published
- publish_failed
- panel_feed_count

هر suppression log شامل source + item_id + event_id + reason + duplicate_of است.

هیچ reason عمومی `duplicate_event` بدون event reference مجاز نیست.

### 13. Panel UX Data Contract

پنل باید حداقل سه نمای داده‌ای داشته باشد:
- «ورودی زنده» — همه خبرهای دیده‌شده امروز با status
- «در انتظار» — فقط editorial queue
- «منتشرشده» — history/auto/manual published

به این ترتیب صفر بودن «در انتظار» دیگر به معنی «هیچ خبری نیامده» نیست.

### 14. Migration

V2 روی همان repo و Telegram secrets فعلی اجرا می‌شود.

Migration steps:
- state/history فعلی حفظ شوند.
- existing published source URLs و news keys برای seed کردن idempotency استفاده شوند.
- event ledger جدید از این به بعد authoritative می‌شود؛ historical reconstruction کامل لازم نیست.
- runtime_v13 تا زمان pass شدن shadow verification دست‌نخورده production می‌ماند.
- V2 ابتدا در shadow mode ingest/dedup می‌کند ولی publish نمی‌کند و تصمیم‌هایش با V1 مقایسه می‌شوند.
- بعد از regression و shadow verification، workflow production به V2 سوئیچ می‌شود.

## تست‌ها

### Unit
- fingerprint actors/actions/locations/facts
- exact duplicate
- same claim multi-source
- material update with changed numbers
- distinct Hormuz events
- airspace close vs reopen
- independent official statements
- Truth post identity/media

### Regression
از failureهای واقعی اخیر fixture ساخته می‌شود، از جمله:
- CENTCOM 92/3/2 counts
- White House total control of Hormuz
- Iran restricted/exclusion zone
- Spain airspace closure for US warplanes
- Iran partial reopen
- Jordan intercepts Iranian missiles
- IAEA/UNSC referral
- airline restore/return to Iranian airspace
- three Iranian tanker strike multi-outlet dedup

### Integration
- fetch → normalize → classify → ledger → panel feed
- publish success updates message_id
- publish failure stays retryable
- auto_publish=true still populates panel live feed
- restart idempotency

### Production verification gate
قبل از اعلام «V2 فعال شد» باید:
1. full test suite green باشد.
2. shadow run چند cycle بدون exception انجام شود.
3. نمونه‌های regression decision درست داشته باشند.
4. panel_live_feed واقعاً non-empty باشد وقتی fresh intake وجود دارد.
5. یک خبر آزمایشی/واقعی مجاز end-to-end با Telegram message_id تأیید شود.
6. logs هیچ silent suppression نداشته باشند.

## Rollback

workflow باید امکان برگشت سریع به runtime_v13 را داشته باشد. تغییر production entrypoint تنها بعد از verification انجام می‌شود؛ V1 تا پایان rollout حذف نمی‌شود.

## خارج از Scope این فاز

- مهاجرت به VPS
- دیتابیس خارجی
- بازطراحی بصری کامل پنل

V2 باید ابتدا روی GitHub Actions پایدار شود؛ بعد همان runtime برای VPS آماده می‌شود.
