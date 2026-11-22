"""All fixed user-facing text (English + Hindi) in one place.

Used when the rules decide on their own (instant path or no Gemini), and as
the hard-coded parts that the LLM is not allowed to change.
Nothing here uses the word "safe" on purpose.
"""

HELPLINE = {
    "en": {"phone": "1930", "website": "https://cybercrime.gov.in",
           "text": "Call 1930 (National Cyber Crime Helpline) or report at cybercrime.gov.in"},
    "hi": {"phone": "1930", "website": "https://cybercrime.gov.in",
           "text": "1930 (राष्ट्रीय साइबर क्राइम हेल्पलाइन) पर कॉल करें या cybercrime.gov.in पर शिकायत करें"},
}

DISCLAIMER = {
    "LOW": {
        "en": "No known scam pattern found. Still, never share your OTP or PIN.",
        "hi": "कोई जाना-पहचाना धोखाधड़ी पैटर्न नहीं मिला। फिर भी, अपना OTP या PIN कभी किसी को न बताएं।",
    },
    "RISKY": {
        "en": "Automated check, it can be wrong. If in doubt, hang up and call 1930.",
        "hi": "यह स्वचालित जाँच है, गलत भी हो सकती है। शक हो तो फ़ोन काटें और 1930 पर कॉल करें।",
    },
}

CATEGORY_LABELS = {
    "digital_arrest": {"en": "Digital arrest scam", "hi": "डिजिटल अरेस्ट धोखाधड़ी"},
    "remote_access": {"en": "Screen-share app scam", "hi": "स्क्रीन-शेयर ऐप धोखाधड़ी"},
    "otp_pin_share": {"en": "OTP / PIN theft", "hi": "OTP / PIN चोरी"},
    "upi_collect": {"en": "Fake 'receive money' UPI request", "hi": "नकली 'पैसे पाएं' UPI रिक्वेस्ट"},
    "sender_mismatch": {"en": "Fake sender name", "hi": "नकली भेजने वाला नाम"},
    "customs_parcel": {"en": "Fake parcel / customs", "hi": "नकली पार्सल / कस्टम्स"},
    "electricity_bill": {"en": "Fake electricity bill", "hi": "नकली बिजली बिल"},
    "kyc_expiry": {"en": "Fake KYC / account block", "hi": "नकली KYC / खाता बंद"},
    "pin_entry": {"en": "UPI PIN request", "hi": "UPI PIN की माँग"},
    "collect_request": {"en": "UPI collect request", "hi": "UPI कलेक्ट रिक्वेस्ट"},
    "suspicious_link": {"en": "Dangerous link", "hi": "खतरनाक लिंक"},
    "prompt_injection": {"en": "Trying to trick the checker", "hi": "जाँच को धोखा देने की कोशिश"},
    "hidden_content": {"en": "Hidden text", "hi": "छिपा हुआ टेक्स्ट"},
    "invisible_chars": {"en": "Invisible characters", "hi": "अदृश्य अक्षर"},
    "ai_exfiltration": {"en": "Data-leak instruction", "hi": "डेटा भेजने का निर्देश"},
    "urgency": {"en": "Pressure tactics", "hi": "जल्दबाज़ी का दबाव"},
}

# When several scams match, the first one in this list is "the" script.
PRIMARY_ORDER = [
    "digital_arrest", "upi_collect", "remote_access", "otp_pin_share", "sender_mismatch",
    "customs_parcel", "electricity_bill", "kyc_expiry", "pin_entry", "collect_request",
    "suspicious_link", "prompt_injection", "ai_exfiltration", "hidden_content",
    "invisible_chars", "urgency",
]


def primary_category(categories: list[str]) -> str | None:
    for cat in PRIMARY_ORDER:
        if cat in categories:
            return cat
    return None


def label(category: str | None, lang: str) -> str | None:
    if category is None or category not in CATEGORY_LABELS:
        return None
    return CATEGORY_LABELS[category][lang]


# ------------------------------------------------------------ call co-pilot
# category -> lang -> (action, why, say_this)
CALL_TEMPLATES = {
    "digital_arrest": {
        "en": ("HANG UP NOW", "Police, CBI or ED never arrest anyone on a video call.",
               "I will go to my local police station myself."),
        "hi": ("अभी फ़ोन काटें", "पुलिस, CBI या ED कभी वीडियो कॉल पर गिरफ्तार नहीं करती।",
               "मैं खुद अपने नज़दीकी थाने जाकर बात करूँगा।"),
    },
    "upi_collect": {
        "en": ("DON'T ENTER PIN, HANG UP", "Entering your UPI PIN always sends money. It never receives.",
               "I don't need a PIN to receive money."),
        "hi": ("PIN न डालें, फ़ोन काटें", "UPI PIN डालने से पैसा हमेशा जाता है, आता नहीं।",
               "पैसे पाने के लिए PIN की ज़रूरत नहीं होती।"),
    },
    "remote_access": {
        "en": ("DON'T INSTALL ANY APP", "Screen-share apps let them see your OTP and bank app.",
               "I don't install apps for strangers. Goodbye."),
        "hi": ("कोई ऐप इंस्टॉल न करें", "ऐसे ऐप से ठग आपका OTP और बैंक ऐप देख लेते हैं।",
               "मैं अनजान लोगों के कहने पर ऐप नहीं डालता। नमस्ते।"),
    },
    "otp_pin_share": {
        "en": ("NEVER SHARE OTP OR PIN", "No bank or officer ever asks for your OTP or PIN.",
               "I don't share OTP. I'll call my bank myself."),
        "hi": ("OTP या PIN कभी न बताएं", "कोई बैंक या अफ़सर कभी OTP या PIN नहीं माँगता।",
               "मैं OTP नहीं बताता। मैं खुद बैंक को फ़ोन करूँगा।"),
    },
    "customs_parcel": {
        "en": ("HANG UP, PARCEL SCAM", "Customs and couriers don't threaten you on calls.",
               "I didn't send any parcel. I'll check with the courier myself."),
        "hi": ("फ़ोन काटें, पार्सल धोखाधड़ी", "कस्टम्स या कूरियर वाले फ़ोन पर धमकी नहीं देते।",
               "मैंने कोई पार्सल नहीं भेजा। मैं खुद कूरियर से पता करूँगा।"),
    },
    "electricity_bill": {
        "en": ("DON'T PAY, CHECK BILL YOURSELF", "Power companies don't cut supply over a phone call.",
               "I'll check my bill on the official app."),
        "hi": ("पैसे न भेजें, बिल खुद देखें", "बिजली कंपनी फ़ोन करके बिजली नहीं काटती।",
               "मैं आधिकारिक ऐप पर अपना बिल देखूँगा।"),
    },
    "kyc_expiry": {
        "en": ("DON'T CLICK, CALL YOUR BANK", "Banks don't block accounts over calls or SMS like this.",
               "I'll visit my branch myself."),
        "hi": ("लिंक न खोलें, बैंक को फ़ोन करें", "बैंक ऐसे कॉल या SMS से खाता बंद नहीं करते।",
               "मैं खुद अपनी ब्रांच जाऊँगा।"),
    },
    "pin_entry": {
        "en": ("DON'T ENTER YOUR PIN", "Entering a UPI PIN means money leaves your account.", None),
        "hi": ("अपना PIN न डालें", "UPI PIN डालने का मतलब है पैसा आपके खाते से जाएगा।", None),
    },
    "collect_request": {
        "en": ("DECLINE THE REQUEST", "Approving a collect request takes money out of your account.", None),
        "hi": ("रिक्वेस्ट मना करें", "कलेक्ट रिक्वेस्ट मंज़ूर करने से पैसा आपके खाते से कटता है।", None),
    },
    "suspicious_link": {
        "en": ("DON'T OPEN THE LINK", "This link can steal your bank details.", None),
        "hi": ("लिंक न खोलें", "यह लिंक आपकी बैंक जानकारी चुरा सकता है।", None),
    },
    "prompt_injection": {
        "en": ("HANG UP NOW", "This text tries to trick our checker. That's a clear scam sign.", None),
        "hi": ("अभी फ़ोन काटें", "यह टेक्स्ट हमारी जाँच को धोखा देने की कोशिश करता है। यह साफ़ धोखाधड़ी का संकेत है।", None),
    },
    "urgency": {
        "en": ("SLOW DOWN, VERIFY FIRST", "Scammers rush you so you don't stop to think.",
               "I'll call you back after checking."),
        "hi": ("रुकें, पहले जाँच करें", "ठग जल्दबाज़ी करवाते हैं ताकि आप सोच न सकें।",
               "मैं जाँच करके वापस फ़ोन करूँगा।"),
    },
    "_DANGEROUS": {
        "en": ("HANG UP NOW", "This looks like a scam call.", None),
        "hi": ("अभी फ़ोन काटें", "यह धोखाधड़ी वाला कॉल लगता है।", None),
    },
    "_SUSPICIOUS": {
        "en": ("PAUSE, VERIFY THE CALLER", "Something here looks like a common scam.",
               "I'll call back on the official number."),
        "hi": ("रुकें, कॉलर की जाँच करें", "इसमें धोखाधड़ी जैसा कुछ दिख रहा है।",
               "मैं आधिकारिक नंबर पर वापस फ़ोन करूँगा।"),
    },
    "_LOW": {
        "en": ("STAY ALERT", "No known scam pattern found. Still, never share your OTP or PIN.", None),
        "hi": ("सतर्क रहें", "कोई जाना-पहचाना धोखाधड़ी पैटर्न नहीं मिला। फिर भी OTP या PIN कभी न बताएं।", None),
    },
}

# ------------------------------------------------------------ UPI guard
AMOUNT_FALLBACK = {"en": "MONEY", "hi": "पैसे"}
AMOUNT_FALLBACK_LOWER = {"en": "money", "hi": "पैसे"}

PAY_HEADLINES = {
    "send_not_receive": {"en": "YOU ARE SENDING {amt} — NOT RECEIVING.",
                         "hi": "आप {amt} भेज रहे हैं — पा नहीं रहे।"},
    "send_pin": {"en": "ENTERING YOUR PIN SENDS {amt} OUT OF YOUR ACCOUNT.",
                 "hi": "PIN डालने का मतलब है आपके खाते से {amt} भेजना।"},
    "sent": {"en": "THIS SAYS {amt} LEFT YOUR ACCOUNT.",
             "hi": "इसके अनुसार आपके खाते से {amt} भेजे गए हैं।"},
    "receiving": {"en": "THIS SAYS YOU RECEIVED {amt}. NO PIN NEEDED.",
                  "hi": "इसके अनुसार आपको {amt} मिले हैं। PIN की ज़रूरत नहीं।"},
    "unknown": {"en": "UNCLEAR WHICH WAY MONEY MOVES. DON'T ENTER YOUR PIN.",
                "hi": "साफ़ नहीं कि पैसा आ रहा है या जा रहा है। PIN न डालें।"},
}

WOULD_MAKE_YOU = {
    "pin": {"en": "Entering your UPI PIN would take {amt} out of your account. You never need a PIN to receive money.",
            "hi": "UPI PIN डालने से {amt} आपके खाते से चले जाएंगे। पैसे पाने के लिए PIN की कभी ज़रूरत नहीं होती।"},
    "sent": {"en": "This message says {amt} already went out. If you didn't do this, call your bank and 1930 now.",
             "hi": "संदेश के अनुसार {amt} जा चुके हैं। अगर यह आपने नहीं किया, तो तुरंत बैंक और 1930 पर कॉल करें।"},
    "received": {"en": "Nothing leaves your account. Money coming in needs no PIN or approval. If anyone now asks for your PIN, it's a scam.",
                 "hi": "आपके खाते से कुछ नहीं जाएगा। पैसे आने के लिए PIN या मंज़ूरी नहीं चाहिए। अब कोई PIN माँगे तो वह धोखाधड़ी है।"},
    "unknown": {"en": "We can't tell. Don't enter your PIN or open any link until you check your bank app yourself.",
                "hi": "पता नहीं चल रहा। अपना बैंक ऐप खुद देखने से पहले PIN न डालें और कोई लिंक न खोलें।"},
}

PAY_NEXT_STEPS = {
    "risky_sending": {
        "en": ["Do not enter your UPI PIN.", "Decline the request in your UPI app.",
               "If you already paid, call 1930 right away.", "Report it at cybercrime.gov.in."],
        "hi": ["अपना UPI PIN न डालें।", "UPI ऐप में रिक्वेस्ट मना (Decline) करें।",
               "अगर पैसे भेज दिए हैं, तो तुरंत 1930 पर कॉल करें।", "cybercrime.gov.in पर शिकायत करें।"],
    },
    "risky_other": {
        "en": ["Don't click links or call numbers in the message.",
               "Check directly in your bank app or official website.",
               "If you shared details or paid, call 1930 right away.", "Report it at cybercrime.gov.in."],
        "hi": ["संदेश के लिंक न खोलें, न उसके नंबर पर कॉल करें।",
               "सीधे अपने बैंक ऐप या आधिकारिक वेबसाइट पर जाँचें।",
               "अगर जानकारी दी या पैसे भेजे हैं, तो तुरंत 1930 पर कॉल करें।", "cybercrime.gov.in पर शिकायत करें।"],
    },
    "low": {
        "en": ["Check the amount in your bank app yourself.", "Never share your OTP or UPI PIN with anyone."],
        "hi": ["राशि अपने बैंक ऐप में खुद देखें।", "अपना OTP या UPI PIN कभी किसी को न बताएं।"],
    },
}

PAY_SHARE = {
    "risky": {"en": "⚠️ Scam alert: I got a fake message ({label}). Never enter your UPI PIN to receive money, a PIN only sends money. Helpline: 1930.",
              "hi": "⚠️ धोखाधड़ी अलर्ट: मुझे एक नकली संदेश मिला ({label})। पैसे पाने के लिए कभी UPI PIN न डालें, PIN से पैसा सिर्फ़ जाता है। हेल्पलाइन: 1930।"},
    "low": {"en": "Checked a payment message with DoubleCheck: no known scam pattern found. Reminder: never share your OTP or UPI PIN.",
            "hi": "DoubleCheck से जाँचा: कोई जाना-पहचाना धोखाधड़ी पैटर्न नहीं मिला। याद रखें: OTP या UPI PIN कभी न बताएं।"},
}

SENDER_MISMATCH_REASON = {
    "en": "Sender says '{sender}' but the UPI ID '{upi}' looks like a personal account. Banks and offices don't use personal IDs.",
    "hi": "भेजने वाला खुद को '{sender}' बताता है, लेकिन UPI ID '{upi}' किसी व्यक्ति का निजी खाता लगता है। बैंक या दफ़्तर निजी ID इस्तेमाल नहीं करते।",
}

# ------------------------------------------------------------ AI guard (English only)
AI_WOULD_MAKE = {
    "risky": "Hidden instructions here could make an AI assistant ignore your request, leak your emails or data, or take actions you didn't ask for.",
    "low": "No hidden instructions found. Still, review what an AI assistant does with content you don't trust.",
}
AI_NEXT_STEPS = {
    "risky": ["Don't give this to an AI assistant as it is.", "Use the cleaned text below instead.",
              "Don't let an AI assistant send emails or open links from this content."],
    "low": ["Use the cleaned text if you want to be extra careful.",
            "Check what an AI assistant does before it sends anything."],
}
AI_SHARE = {
    "risky": "⚠️ Heads-up: this email/page hides instructions aimed at AI assistants. Don't feed it to your AI tools.",
    "low": "Checked with DoubleCheck AI guard: no hidden AI instructions found.",
}
