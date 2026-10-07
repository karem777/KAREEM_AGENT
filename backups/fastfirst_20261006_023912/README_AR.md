# KAREEM_AGENT COMPLETE 1.0

دي طبقة المعمارية الكاملة للإيجنت: مش موقع-بموقع، ومش مجرد Planner أكبر. الهدف إن `Qwen3:8b` يشتغل داخل حلقة إدراك/قرار/تنفيذ/تحقق، مع World Model عام للويب، بحث عميق عن المشاريع والوثائق، ذاكرة خبرات، ومنظومة Windows Native.

## ماذا تضيف

- 80 خطوة تشغيل كحد أقصى، والـRunner يوقف نفسه فور تحقق الهدف.
- Goal Contract عام بدل تحويل الطلب مباشرة إلى selectors أو خطوات ثابتة.
- World State يحتوي URL/origin/page type/elements/results/evidence/fingerprint.
- Browser actions لها postconditions والتحقق التلقائي بعد التغييرات.
- منع تكرار نفس الفعل على نفس الحالة، مع Recovery حقيقي.
- Research Engine يبحث في GitHub ويقرأ README ويقارن ويرتب المشاريع بدل مجرد فتح صفحة.
- Experience Memory تحفظ trajectory/lesson/outcome، ويمكن استرجاعها في المهام التالية.
- Windows Native Tool: system info, processes, services, network, storage, installed apps, env, events, PowerShell، فتح/إغلاق البرامج، وعمليات كتابة/تعديل محلية مع حواجز أمان.
- تكامل اختياري تلقائي مع `tools.browser`, `tools.desktop`, `tools.filesystem`, `tools.system`, `tools.web` الموجودة أصلًا.
- واجهة Flask مستقلة `app_complete.py` حتى نختبر النسخة الجديدة بدون تدمير النسخة الحالية.

## مهم

النسخة لا تستبدل `tools/browser.py` الموجودة عندك. هي تستخدم BrowserTool الحالية إن وجدت، وبالتالي تحافظ على حماية Chrome التي وصلتم بها لنجاح Google -> Search -> First Result -> OpenAI.

## التشغيل

من داخل `C:\Users\Acer\KAREEM_AGENT`:

```powershell
Copy-Item -Recurse -Force "<مكان الحزمة>\brain\complete_*" .\brain\
Copy-Item -Recurse -Force "<مكان الحزمة>\core\complete_*" .\core\
Copy-Item -Recurse -Force "<مكان الحزمة>\tools\complete_*" .\tools\
Copy-Item -Recurse -Force "<مكان الحزمة>\tests\*" .\tests\
Copy-Item -Recurse -Force "<مكان الحزمة>\app_complete.py" .\
```

أو شغّل `install_complete.ps1` من داخل مجلد المشروع.

ثم:

```powershell
.\.venv\Scripts\python.exe app_complete.py
```

الواجهة تعمل على `http://127.0.0.1:5000` ما لم يكن المنفذ مستخدمًا؛ وقتها استخدم `KAREEM_PORT=5001`.

## أمثلة

```text
ادخل جوجل وابحث عن OpenAI وافتح أول نتيجة
```

```text
ادخل الموقع ده وهاتلي أرخص 5 لابتوبات RTX 4060 تحت 4000 ريال وقارن بينهم
```

```text
ابحث في GitHub عن أقوى مشاريع Agents تشتغل كويس مع Qwen3:8b على Windows، قارنهم واختار أفضل أفكار نقدر نركبها في KAREEM_AGENT
```

```text
حلل حالة الجهاز، اكتشف سبب بطء الشبكة، وافتح لي التقرير من غير ما تغيّر أي إعداد حساس
```

## وضع البحث العميق

الأداة `research.deep_research` تدعم ميزانية زمنية تصل إلى 60 دقيقة. الـPlanner لا يستدعيها تلقائيًا لكل مهمة؛ يستدعيها عندما يحتاج جمع معلومات خارجية متعدد المصادر. النتيجة التي ترجع للإيجنت ليست صفحة ويب فقط: هي مصادر + evidence + score + extracted patterns + compatibility مع الموديل الحالي.

## السلامة

التشخيص والقراءة المحلية متاحة مباشرة. العمليات التدميرية أو التغييرات الحساسة ترجع `approval_required` أو تحتاج `confirm=true`، والـRunner لا يفترض الموافقة من نفسه.
