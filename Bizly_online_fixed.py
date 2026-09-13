import streamlit as st
import requests
import sqlite3
import hashlib
import hmac
import os
from io import BytesIO
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER
st.set_page_config(
    page_title="Bizly - Smart Business Assistant",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)


# =========================================================
# BIZLY - COMPLETE LOCAL OLLAMA APP
# =========================================================

BACKEND_URL = "https://bizly-backend.onrender.com"

SYSTEM_PROMPT = """
You are Bizly, a fast and practical AI business assistant.

Help with:
- Business
- Sales and marketing
- Customer replies
- Quotations
- GST/invoice basics
- Export and import basics
- Business strategy

Rules:
- Be concise and useful.
- Reply in the user's language.
- Never invent prices, GST rates, documents, stock or facts.
- If important information is missing, ask for it.
- For tax/GST/export compliance, clearly say that current rules should be verified with official authorities or a tax professional.
"""


# =========================================================
# LOCAL ACCOUNT + BUSINESS PROFILE DATABASE
# =========================================================
DB_FILE = "bizly_users.db"

def init_db():
    # Create the database if it does not exist.
    # If an older Bizly database already exists, add any new profile
    # columns without deleting existing login accounts.
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            business_name TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            business_type TEXT DEFAULT '',
            city TEXT DEFAULT '',
            state TEXT DEFAULT '',
            gstin TEXT DEFAULT '',
            address TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Migration for the older login-only database.
    existing = {row[1] for row in cur.execute("PRAGMA table_info(users)").fetchall()}
    new_columns = {
        "business_name": "TEXT DEFAULT ''",
        "phone": "TEXT DEFAULT ''",
        "business_type": "TEXT DEFAULT ''",
        "city": "TEXT DEFAULT ''",
        "state": "TEXT DEFAULT ''",
        "gstin": "TEXT DEFAULT ''",
        "address": "TEXT DEFAULT ''",
        "created_at": "TEXT DEFAULT CURRENT_TIMESTAMP",
    }
    for column, definition in new_columns.items():
        if column not in existing:
            cur.execute(f"ALTER TABLE users ADD COLUMN {column} {definition}")

    conn.commit()
    conn.close()

# Run database setup/migration before login or profile functions are used.
init_db()

def make_password_hash(password, salt=None):
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, 200000
    )
    return digest.hex(), salt.hex()

def create_account(name, email, password):
    email = email.strip().lower()
    password_hash, salt = make_password_hash(password)
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.execute(
            """INSERT INTO users
               (name, email, password_hash, salt)
               VALUES (?, ?, ?, ?)""",
            (name.strip(), email, password_hash, salt)
        )
        conn.commit()
        conn.close()
        return True, "Account created."
    except sqlite3.IntegrityError:
        return False, "An account with this email already exists."
    except Exception as error:
        return False, str(error)

def check_login(email, password):
    email = email.strip().lower()
    conn = sqlite3.connect(DB_FILE)
    row = conn.execute(
        """SELECT id, name, email, password_hash, salt,
                  business_name, phone, business_type, city, state,
                  gstin, address
           FROM users WHERE email = ?""",
        (email,)
    ).fetchone()
    conn.close()

    if not row:
        return None

    expected, _ = make_password_hash(
        password, bytes.fromhex(row[4])
    )
    if not hmac.compare_digest(expected, row[3]):
        return None

    return {
        "id": row[0], "name": row[1], "email": row[2],
        "business_name": row[5], "phone": row[6],
        "business_type": row[7], "city": row[8], "state": row[9],
        "gstin": row[10], "address": row[11]
    }

def get_profile(user_id):
    conn = sqlite3.connect(DB_FILE)
    row = conn.execute(
        """SELECT name, email, business_name, phone, business_type,
                  city, state, gstin, address
           FROM users WHERE id = ?""",
        (user_id,)
    ).fetchone()
    conn.close()
    if not row:
        return {}
    keys = [
        "name", "email", "business_name", "phone", "business_type",
        "city", "state", "gstin", "address"
    ]
    return dict(zip(keys, row))

def save_profile(user_id, name, business_name, phone, business_type,
                 city, state, gstin, address):
    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        """UPDATE users
           SET name=?, business_name=?, phone=?, business_type=?,
               city=?, state=?, gstin=?, address=?
           WHERE id=?""",
        (name.strip(), business_name.strip(), phone.strip(),
         business_type, city.strip(), state.strip(), gstin.strip(),
         address.strip(), user_id)
    )
    conn.commit()
    conn.close()

def auth_screen():
    st.markdown("""
    <div class="bizly-hero">
        <span class="bizly-badge">💼 Bizly</span>
        <div class="bizly-title">
            Your <span class="bizly-gradient">Smart Business Assistant</span>
        </div>
        <div class="bizly-subtitle">
            Sign in to continue, or create your free Bizly account.
        </div>
    </div>
    """, unsafe_allow_html=True)

    login_tab, signup_tab = st.tabs(["🔐 Login", "✨ Sign Up"])

    with login_tab:
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password",
                                  key="login_password")
        if st.button("🔐 Login", type="primary",
                     use_container_width=True):
            if not email or not password:
                st.warning("Please enter email and password.")
            else:
                user = check_login(email, password)
                if user:
                    st.session_state.authenticated = True
                    st.session_state.user_id = user["id"]
                    st.session_state.user_name = user["name"]
                    st.session_state.user_email = user["email"]
                    st.session_state.page = "Home"
                    st.rerun()
                else:
                    st.error("Invalid email or password.")

    with signup_tab:
        name = st.text_input("Your Name", key="signup_name")
        email = st.text_input("Email", key="signup_email")
        password = st.text_input("Password", type="password",
                                 key="signup_password")
        confirm = st.text_input("Confirm Password", type="password",
                                key="signup_confirm")
        st.caption("For local testing, accounts are stored in a local SQLite database.")

        if st.button("✨ Create Account", type="primary",
                     use_container_width=True):
            if not name.strip() or not email.strip() or not password:
                st.warning("Please fill all fields.")
            elif "@" not in email:
                st.warning("Please enter a valid email.")
            elif len(password) < 6:
                st.warning("Password must be at least 6 characters.")
            elif password != confirm:
                st.warning("Passwords do not match.")
            else:
                ok, message = create_account(name, email, password)
                if ok:
                    st.success("Account created! Now login.")
                else:
                    st.error(message)

init_db()

# =========================================================
# DESIGN
# =========================================================

st.markdown("""
<style>
.stApp {
    background: linear-gradient(135deg,#f7f9ff 0%,#eef3ff 55%,#f8fbff 100%);
}
.block-container {
    max-width: 1450px;
    padding-top: 1.5rem;
    padding-bottom: 3rem;
}
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg,#0b1224 0%,#111d3a 55%,#0b142b 100%);
}
section[data-testid="stSidebar"] * {
    color:#f4f7ff;
}
section[data-testid="stSidebar"] .stButton > button {
    background:rgba(255,255,255,.07);
    border:1px solid rgba(255,255,255,.08);
    color:white;
    border-radius:12px;
    min-height:44px;
}
section[data-testid="stSidebar"] .stButton > button:hover {
    background:rgba(82,111,255,.30);
}
.bizly-hero {
    padding:30px 32px;
    border-radius:28px;
    background:radial-gradient(circle at 85% 20%,rgba(92,104,255,.18),transparent 28%),
               linear-gradient(135deg,#fff 0%,#f0f4ff 100%);
    border:1px solid #dce4ff;
    box-shadow:0 18px 50px rgba(40,65,130,.10);
    margin-bottom:24px;
}
.bizly-badge {
    display:inline-block;
    padding:8px 14px;
    border-radius:999px;
    background:#edf1ff;
    color:#3154d8;
    font-weight:700;
}
.bizly-title {
    font-size:clamp(40px,5vw,68px);
    line-height:1.02;
    font-weight:850;
    color:#101a38;
    margin:18px 0 12px;
}
.bizly-gradient {
    background:linear-gradient(90deg,#3154d8,#6947d9);
    -webkit-background-clip:text;
    -webkit-text-fill-color:transparent;
}
.bizly-subtitle {
    font-size:20px;
    color:#60708f;
    max-width:850px;
}
.card {
    padding:22px;
    min-height:155px;
    border-radius:22px;
    background:rgba(255,255,255,.88);
    border:1px solid #dce4f5;
    box-shadow:0 10px 30px rgba(50,70,120,.08);
}
.card h3 {
    color:#172342;
    margin-bottom:8px;
}
.card p {
    color:#687793;
    line-height:1.5;
}
.stButton > button, .stDownloadButton > button {
    border-radius:13px;
    min-height:44px;
    font-weight:700;
}
.small-note {
    color:#687793;
    font-size:13px;
}
@media(max-width:768px) {
    .block-container {
        padding:1rem .8rem 2rem;
    }
    .bizly-hero {
        padding:22px 20px;
        border-radius:22px;
    }
    .bizly-title {
        font-size:40px;
    }
}
</style>
""", unsafe_allow_html=True)

# =========================================================
# SESSION STATE
# =========================================================

if "page" not in st.session_state:
    st.session_state.page = "Home"

if "messages" not in st.session_state:
    st.session_state.messages = []

if "history" not in st.session_state:
    st.session_state.history = []

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if "user_id" not in st.session_state:
    st.session_state.user_id = None

if "user_name" not in st.session_state:
    st.session_state.user_name = ""

if "user_email" not in st.session_state:
    st.session_state.user_email = ""

if "profile" not in st.session_state:
    st.session_state.profile = {}

if st.session_state.authenticated and st.session_state.user_id:
    st.session_state.profile = get_profile(st.session_state.user_id)

def go(page):
    st.session_state.page = page
    st.rerun()

# =========================================================
# ONLINE BIZLY BACKEND
# =========================================================

def ask_ollama(messages, fast=False):
    try:
        response = requests.post(
            f"{BACKEND_URL}/chat",
            json={
                "messages": [
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT
                    }
                ] + messages,
                "fast": fast
            },
            timeout=120
        )

        if response.status_code != 200:
            return f"Backend error: {response.text}"

        data = response.json()

        if "error" in data:
            return f"Backend error: {data['error']}"

        return data.get("response", "No response received.")

    except requests.exceptions.RequestException as error:
        return f"Bizly couldn't connect to online backend: {error}"


def run_prompt(prompt, fast=False):
    return ask_ollama(
        [{"role": "user", "content": prompt}],
        fast=fast
    )


def show_ollama_error(error):
    st.error("Bizly could not connect to the online backend.")
    st.code(str(error))


# =========================================================
# LOGIN GATE
# =========================================================
if not st.session_state.authenticated:
    auth_screen()
    st.stop()

# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:
    st.markdown("## 💼 Bizly")
    st.caption("Your Smart Business Assistant")
    st.divider()

    if st.button("🏠 Home", use_container_width=True):
        go("Home")

    if st.button("💬 New Chat", use_container_width=True):
        st.session_state.messages = []
        go("Chat")

    if st.button("⚡ Fast Reply", use_container_width=True):
        go("Fast Reply")

    if st.button("🧾 Quotation", use_container_width=True):
        go("Quotation")

    if st.button("🧾 GST Bill", use_container_width=True):
        go("GST Bill")

    if st.button("📊 Sales & Marketing", use_container_width=True):
        go("Sales & Marketing")

    if st.button("💬 Customer Reply", use_container_width=True):
        go("Customer Reply")

    if st.button("🌍 Export Help", use_container_width=True):
        go("Export Help")

    st.divider()
    profile = st.session_state.profile or {}
    st.markdown("### 👤 Account")
    st.caption(st.session_state.user_name)
    if profile.get("business_name"):
        st.caption("🏢 " + profile["business_name"])

    if st.button("👤 Business Profile", use_container_width=True):
        go("Business Profile")

    if st.button("🚪 Logout", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.user_id = None
        st.session_state.user_name = ""
        st.session_state.user_email = ""
        st.session_state.profile = {}
        st.session_state.messages = []
        st.session_state.history = []
        st.rerun()

    st.divider()
    st.markdown("### 🔎 Recent History")

    if st.session_state.history:
        for item in st.session_state.history[-8:][::-1]:
            st.caption("• " + item[:70])
    else:
        st.caption("No searches yet.")

# =========================================================
# BUSINESS PROFILE
# =========================================================
if st.session_state.page == "Business Profile":
    st.title("👤 Business Profile")
    st.caption("Save your business details once. Bizly can reuse them in documents.")

    profile = get_profile(st.session_state.user_id)

    with st.form("business_profile_form"):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Your Name", value=profile.get("name", ""))
            business_name = st.text_input(
                "Business / Company Name",
                value=profile.get("business_name", "")
            )
            phone = st.text_input("Phone Number", value=profile.get("phone", ""))
            business_type = st.selectbox(
                "Business Type",
                [
                    "Manufacturer", "Trader", "Exporter",
                    "Importer", "Service", "Retail", "Other"
                ],
                index=(
                    [
                        "Manufacturer", "Trader", "Exporter",
                        "Importer", "Service", "Retail", "Other"
                    ].index(profile.get("business_type"))
                    if profile.get("business_type") in [
                        "Manufacturer", "Trader", "Exporter",
                        "Importer", "Service", "Retail", "Other"
                    ] else 0
                )
            )

        with col2:
            city = st.text_input("City", value=profile.get("city", ""))
            state = st.text_input(
                "State",
                value=profile.get("state", "Uttar Pradesh")
            )
            gstin = st.text_input(
                "GSTIN (optional)",
                value=profile.get("gstin", "")
            )
            address = st.text_area(
                "Business Address",
                value=profile.get("address", ""),
                height=120
            )

        submitted = st.form_submit_button(
            "💾 Save Business Profile",
            type="primary",
            use_container_width=True
        )

    if submitted:
        save_profile(
            st.session_state.user_id,
            name, business_name, phone, business_type,
            city, state, gstin, address
        )
        st.session_state.user_name = name.strip()
        st.session_state.profile = get_profile(st.session_state.user_id)
        st.success("Business profile saved successfully.")
        st.rerun()

    st.info(
        "Tip: GSTIN and business address are optional here, "
        "but adding them makes GST Bill creation faster."
    )

# =========================================================
# HOME
# =========================================================

if st.session_state.page == "Home":

    st.markdown("""
    <div class="bizly-hero">
        <span class="bizly-badge">⚡ Fast • Practical • Business-focused</span>
        <div class="bizly-title">
            Welcome to <span class="bizly-gradient">Bizly</span>
        </div>
        <div class="bizly-subtitle">
            Your smart business assistant for chat, fast replies,
            sales, customer communication, quotations, GST bills
            and export help.
        </div>
    </div>
    """, unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown(
            '<div class="card"><h3>💬 AI Chat</h3>'
            '<p>Ask Bizly practical questions about your business.</p></div>',
            unsafe_allow_html=True
        )
        st.write("")
        if st.button("Open Chat →", use_container_width=True):
            go("Chat")

    with c2:
        st.markdown(
            '<div class="card"><h3>⚡ Fast Reply</h3>'
            '<p>Get short, direct business replies quickly.</p></div>',
            unsafe_allow_html=True
        )
        st.write("")
        if st.button("Try Fast Reply →", use_container_width=True):
            go("Fast Reply")

    with c3:
        st.markdown(
            '<div class="card"><h3>📊 Sales & Marketing</h3>'
            '<p>Create practical ideas to reach customers and increase sales.</p></div>',
            unsafe_allow_html=True
        )
        st.write("")
        if st.button("Open Sales →", use_container_width=True):
            go("Sales & Marketing")

    st.write("")

    c4, c5, c6 = st.columns(3)

    with c4:
        st.markdown(
            '<div class="card"><h3>💬 Customer Reply</h3>'
            '<p>Create professional replies for WhatsApp or email.</p></div>',
            unsafe_allow_html=True
        )
        st.write("")
        if st.button("Open Replies →", use_container_width=True):
            go("Customer Reply")

    with c5:
        st.markdown(
            '<div class="card"><h3>🧾 Quotation & GST Bill</h3>'
            '<p>Create business documents and download PDFs.</p></div>',
            unsafe_allow_html=True
        )
        st.write("")
        if st.button("Open Billing →", use_container_width=True):
            go("GST Bill")

    with c6:
        st.markdown(
            '<div class="card"><h3>🌍 Export Help</h3>'
            '<p>Understand export procedures and buyer communication.</p></div>',
            unsafe_allow_html=True
        )
        st.write("")
        if st.button("Open Export Help →", use_container_width=True):
            go("Export Help")

# =========================================================
# CHAT
# =========================================================

elif st.session_state.page == "Chat":

    st.title("💬 Chat with Bizly")
    st.caption("Ask your business question.")

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    prompt = st.chat_input("Ask Bizly anything...")

    if prompt:
        st.session_state.messages.append(
            {"role": "user", "content": prompt}
        )

        with st.chat_message("user"):
            st.markdown(prompt)

        try:
            with st.chat_message("assistant"):
                with st.spinner("Bizly is thinking..."):
                    answer = ask_ollama(
                        st.session_state.messages
                    )
                st.markdown(answer)

            st.session_state.messages.append(
                {"role": "assistant", "content": answer}
            )
            st.session_state.history.append(prompt)

        except Exception as error:
            show_ollama_error(error)

# =========================================================
# FAST REPLY
# =========================================================

elif st.session_state.page == "Fast Reply":

    st.title("⚡ Fast Reply")
    st.caption("Short, direct answers for everyday business needs.")

    prompt = st.text_area(
        "What do you need a quick reply for?",
        height=140,
        placeholder=(
            "Example: Customer is asking for our best price."
        )
    )

    if st.button(
        "⚡ Generate Fast Reply",
        type="primary",
        use_container_width=True
    ):
        if not prompt.strip():
            st.warning("Please enter your request.")
        else:
            try:
                with st.spinner("Generating fast reply..."):
                    answer = run_prompt(
                        """Give a very short, direct and useful
business reply. Keep it to 2-4 sentences maximum.

User request:
""" + prompt,
                        fast=True
                    )

                st.success("Fast Reply")
                st.write(answer)
                st.session_state.history.append(prompt)

            except Exception as error:
                show_ollama_error(error)

# =========================================================
# SALES & MARKETING
# =========================================================

elif st.session_state.page == "Sales & Marketing":

    st.title("📊 Sales & Marketing")

    business = st.text_input("Business")
    product = st.text_input("Product / Service")
    target = st.text_input("Target Customer")

    platform = st.selectbox(
        "Platform",
        ["Instagram", "WhatsApp", "Facebook", "Google", "Multiple"]
    )

    goal = st.selectbox(
        "Goal",
        [
            "More Sales",
            "More Customers",
            "More Leads",
            "Brand Awareness"
        ]
    )

    if st.button(
        "🚀 Generate Plan",
        type="primary",
        use_container_width=True
    ):
        if not business or not product:
            st.warning("Please enter your business and product.")
        else:
            prompt = f"""
Create a practical sales and marketing plan.

Business: {business}
Product/service: {product}
Target customer: {target or "Not specified"}
Platform: {platform}
Goal: {goal}

Give:
1. 3 practical ideas
2. 2 sample posts/messages
3. A simple call-to-action
Keep it concise.
"""
            try:
                with st.spinner("Creating plan..."):
                    answer = run_prompt(prompt)

                st.markdown(answer)
                st.session_state.history.append(product)

            except Exception as error:
                show_ollama_error(error)

# =========================================================
# CUSTOMER REPLY
# =========================================================

elif st.session_state.page == "Customer Reply":

    st.title("💬 Customer Reply")

    customer_message = st.text_area(
        "Customer Message",
        height=180,
        placeholder="Paste the customer's message here..."
    )

    language = st.selectbox(
        "Language",
        ["Same as customer", "English", "Hindi"]
    )

    tone = st.selectbox(
        "Tone",
        ["Professional", "Friendly", "Short"]
    )

    channel = st.selectbox(
        "Channel",
        ["WhatsApp", "Email"]
    )

    if st.button(
        "✍️ Generate Reply",
        type="primary",
        use_container_width=True
    ):
        if not customer_message.strip():
            st.warning("Please enter the customer's message.")
        else:
            prompt = f"""
Write a ready-to-send customer reply.

Customer message:
{customer_message}

Language: {language}
Tone: {tone}
Channel: {channel}

Return only the reply.
"""
            try:
                with st.spinner("Writing reply..."):
                    answer = run_prompt(prompt, fast=True)

                st.success("Ready to send")
                st.write(answer)
                st.session_state.history.append(customer_message)

            except Exception as error:
                show_ollama_error(error)

# =========================================================
# QUOTATION PDF
# =========================================================

elif st.session_state.page == "Quotation":

    st.title("🧾 Quotation")
    st.caption("Create a simple professional quotation PDF.")

    customer = st.text_input("Customer / Company")
    customer_address = st.text_area("Customer Address", height=80)
    product = st.text_input("Product")

    col1, col2 = st.columns(2)

    with col1:
        quantity = st.number_input(
            "Quantity",
            min_value=1,
            value=1,
            step=1
        )
        price = st.number_input(
            "Price per unit (₹)",
            min_value=0.0,
            value=0.0,
            step=1.0
        )

    with col2:
        payment = st.text_input(
            "Payment Terms",
            value="As agreed"
        )
        delivery = st.text_input(
            "Delivery Terms",
            value="As agreed"
        )

    if st.button(
        "🧾 Generate Quotation PDF",
        type="primary",
        use_container_width=True
    ):
        if not customer or not product:
            st.warning("Please enter customer and product.")
        else:
            total = quantity * price
            quote_id = "BIZ-" + datetime.now().strftime(
                "%Y%m%d%H%M%S"
            )

            buffer = BytesIO()

            doc = SimpleDocTemplate(
                buffer,
                pagesize=A4,
                rightMargin=40,
                leftMargin=40,
                topMargin=40,
                bottomMargin=40
            )

            styles = getSampleStyleSheet()
            title_style = styles["Title"]
            title_style.alignment = TA_CENTER

            story = [
                Paragraph("BIZLY", title_style),
                Paragraph(
                    "Business Quotation",
                    styles["Heading2"]
                ),
                Spacer(1, 12),
                Paragraph(
                    f"<b>Quotation ID:</b> {quote_id}",
                    styles["Normal"]
                ),
                Paragraph(
                    f"<b>Date:</b> {datetime.now().strftime('%d-%m-%Y')}",
                    styles["Normal"]
                ),
                Paragraph(
                    f"<b>Customer:</b> {customer}",
                    styles["Normal"]
                ),
                Paragraph(
                    f"<b>Address:</b> {customer_address or '-'}",
                    styles["Normal"]
                ),
                Spacer(1, 18)
            ]

            table_data = [
                ["Product", "Quantity", "Unit Price", "Total"],
                [
                    product,
                    str(quantity),
                    f"₹{price:,.2f}",
                    f"₹{total:,.2f}"
                ]
            ]

            table = Table(
                table_data,
                colWidths=[220, 70, 100, 100]
            )

            table.setStyle(
                TableStyle([
                    (
                        "BACKGROUND",
                        (0, 0), (-1, 0),
                        colors.HexColor("#3154d8")
                    ),
                    (
                        "TEXTCOLOR",
                        (0, 0), (-1, 0),
                        colors.white
                    ),
                    (
                        "GRID",
                        (0, 0), (-1, -1),
                        0.5, colors.grey
                    ),
                    (
                        "PADDING",
                        (0, 0), (-1, -1),
                        8
                    )
                ])
            )

            story += [
                table,
                Spacer(1, 18),
                Paragraph(
                    f"<b>Payment Terms:</b> {payment}",
                    styles["Normal"]
                ),
                Paragraph(
                    f"<b>Delivery Terms:</b> {delivery}",
                    styles["Normal"]
                ),
                Spacer(1, 18),
                Paragraph(
                    f"<b>Grand Total: ₹{total:,.2f}</b>",
                    styles["Heading3"]
                )
            ]

            doc.build(story)
            buffer.seek(0)

            st.success("Quotation created.")

            st.download_button(
                "⬇️ Download Bizly Quotation",
                buffer,
                file_name="Bizly_Quotation.pdf",
                mime="application/pdf",
                use_container_width=True
            )

# =========================================================
# GST BILL
# =========================================================

elif st.session_state.page == "GST Bill":

    st.title("🧾 GST Bill")
    st.caption(
        "Create a GST tax invoice PDF. Enter the actual GST details "
        "for your business and customer."
    )

    st.markdown("### 🏢 Seller Details")

    seller_col1, seller_col2 = st.columns(2)

    with seller_col1:
        seller_name = st.text_input(
            "Business / Seller Name",
            value=st.session_state.profile.get("business_name", "")
        )
        seller_gstin = st.text_input(
            "Seller GSTIN",
            value=st.session_state.profile.get("gstin", ""),
            placeholder="Example: 22AAAAA0000A1Z5"
        )
        seller_state = st.text_input(
            "Seller State",
            value=st.session_state.profile.get("state", "Uttar Pradesh")
        )

    with seller_col2:
        seller_address = st.text_area(
            "Seller Address",
            value=st.session_state.profile.get("address", ""),
            height=100
        )
        invoice_number = st.text_input(
            "Invoice Number",
            value="BIZ-" + datetime.now().strftime(
                "%Y%m%d%H%M"
            )
        )
        invoice_date = st.date_input(
            "Invoice Date",
            value=datetime.now().date()
        )

    st.divider()

    st.markdown("### 👤 Customer Details")

    customer_col1, customer_col2 = st.columns(2)

    with customer_col1:
        buyer_name = st.text_input(
            "Customer / Buyer Name"
        )
        buyer_gstin = st.text_input(
            "Customer GSTIN (optional)"
        )

    with customer_col2:
        buyer_address = st.text_area(
            "Customer Address",
            height=100
        )
        buyer_state = st.text_input(
            "Customer State"
        )

    st.divider()

    st.markdown("### 📦 Item Details")

    item_col1, item_col2, item_col3 = st.columns(3)

    with item_col1:
        item_name = st.text_input(
            "Product / Item"
        )

    with item_col2:
        hsn = st.text_input(
            "HSN / SAC"
        )

    with item_col3:
        quantity = st.number_input(
            "Quantity",
            min_value=0.01,
            value=1.0,
            step=1.0
        )

    price_col1, price_col2 = st.columns(2)

    with price_col1:
        unit_price = st.number_input(
            "Price per unit (₹)",
            min_value=0.0,
            value=0.0,
            step=1.0
        )

    with price_col2:
        gst_rate = st.number_input(
            "GST Rate (%)",
            min_value=0.0,
            max_value=100.0,
            value=18.0,
            step=1.0
        )

    tax_type = st.radio(
        "Tax Type",
        [
            "CGST + SGST (same-state)",
            "IGST (inter-state)"
        ],
        horizontal=True
    )

    payment_terms = st.text_input(
        "Payment Terms",
        value="As agreed"
    )

    delivery_terms = st.text_input(
        "Delivery Terms",
        value="As agreed"
    )

    st.markdown(
        '<p class="small-note">'
        'GST rate should be entered according to the applicable rate '
        'for the actual product/service. Verify tax compliance before '
        'issuing an invoice.'
        '</p>',
        unsafe_allow_html=True
    )

    if st.button(
        "🧾 Generate GST Bill PDF",
        type="primary",
        use_container_width=True
    ):

        if not seller_name or not seller_address:
            st.warning(
                "Please enter seller name and seller address."
            )
        elif not buyer_name or not item_name:
            st.warning(
                "Please enter customer name and product."
            )
        else:
            taxable_value = quantity * unit_price
            gst_amount = taxable_value * gst_rate / 100
            grand_total = taxable_value + gst_amount

            if tax_type.startswith("CGST"):
                cgst = gst_amount / 2
                sgst = gst_amount / 2
                igst = 0
            else:
                cgst = 0
                sgst = 0
                igst = gst_amount

            buffer = BytesIO()

            doc = SimpleDocTemplate(
                buffer,
                pagesize=A4,
                rightMargin=30,
                leftMargin=30,
                topMargin=30,
                bottomMargin=30
            )

            styles = getSampleStyleSheet()

            title_style = styles["Title"]
            title_style.alignment = TA_CENTER

            story = [
                Paragraph("BIZLY", title_style),
                Paragraph(
                    "TAX INVOICE / GST BILL",
                    styles["Heading2"]
                ),
                Spacer(1, 12)
            ]

            seller_data = [
                [
                    Paragraph(
                        "<b>Seller Details</b>",
                        styles["Normal"]
                    ),
                    Paragraph(
                        "<b>Invoice Details</b>",
                        styles["Normal"]
                    )
                ],
                [
                    f"{seller_name}<br/>{seller_address}<br/>"
                    f"GSTIN: {seller_gstin or '-'}<br/>"
                    f"State: {seller_state or '-'}",
                    f"Invoice No: {invoice_number}<br/>"
                    f"Invoice Date: {invoice_date.strftime('%d-%m-%Y')}"
                ]
            ]

            seller_table = Table(
                seller_data,
                colWidths=[270, 270]
            )

            seller_table.setStyle(
                TableStyle([
                    ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
                    ("BACKGROUND", (0,0), (-1,0),
                     colors.HexColor("#eaf0ff")),
                    ("VALIGN", (0,0), (-1,-1), "TOP"),
                    ("PADDING", (0,0), (-1,-1), 8)
                ])
            )

            story += [
                seller_table,
                Spacer(1, 12)
            ]

            buyer_data = [
                [
                    Paragraph(
                        "<b>Customer / Buyer Details</b>",
                        styles["Normal"]
                    ),
                    ""
                ],
                [
                    f"{buyer_name}<br/>{buyer_address or '-'}<br/>"
                    f"GSTIN: {buyer_gstin or '-'}",
                    f"State: {buyer_state or '-'}"
                ]
            ]

            buyer_table = Table(
                buyer_data,
                colWidths=[270, 270]
            )

            buyer_table.setStyle(
                TableStyle([
                    ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
                    ("BACKGROUND", (0,0), (-1,0),
                     colors.HexColor("#eaf0ff")),
                    ("VALIGN", (0,0), (-1,-1), "TOP"),
                    ("PADDING", (0,0), (-1,-1), 8)
                ])
            )

            story += [
                buyer_table,
                Spacer(1, 14)
            ]

            item_data = [
                [
                    "Item",
                    "HSN/SAC",
                    "Qty",
                    "Rate",
                    "Taxable",
                    "GST",
                    "Total"
                ],
                [
                    item_name,
                    hsn or "-",
                    f"{quantity:g}",
                    f"₹{unit_price:,.2f}",
                    f"₹{taxable_value:,.2f}",
                    f"{gst_rate:g}%",
                    f"₹{grand_total:,.2f}"
                ]
            ]

            item_table = Table(
                item_data,
                colWidths=[130, 65, 45, 70, 75, 45, 80]
            )

            item_table.setStyle(
                TableStyle([
                    ("BACKGROUND", (0,0), (-1,0),
                     colors.HexColor("#3154d8")),
                    ("TEXTCOLOR", (0,0), (-1,0), colors.white),
                    ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
                    ("PADDING", (0,0), (-1,-1), 6),
                    ("FONTSIZE", (0,0), (-1,-1), 8)
                ])
            )

            story += [
                item_table,
                Spacer(1, 14)
            ]

            tax_rows = [
                ["Taxable Value", f"₹{taxable_value:,.2f}"]
            ]

            if cgst > 0:
                tax_rows.append(
                    [f"CGST ({gst_rate/2:g}%)",
                     f"₹{cgst:,.2f}"]
                )
                tax_rows.append(
                    [f"SGST ({gst_rate/2:g}%)",
                     f"₹{sgst:,.2f}"]
                )
            else:
                tax_rows.append(
                    [f"IGST ({gst_rate:g}%)",
                     f"₹{igst:,.2f}"]
                )

            tax_rows.append(
                ["Grand Total", f"₹{grand_total:,.2f}"]
            )

            tax_table = Table(
                tax_rows,
                colWidths=[380, 150],
                hAlign="RIGHT"
            )

            tax_table.setStyle(
                TableStyle([
                    ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
                    ("PADDING", (0,0), (-1,-1), 7),
                    ("BACKGROUND", (0,-1), (-1,-1),
                     colors.HexColor("#eaf0ff")),
                    ("FONTNAME", (0,-1), (-1,-1), "Helvetica-Bold")
                ])
            )

            story += [
                tax_table,
                Spacer(1, 14),
                Paragraph(
                    f"<b>Payment Terms:</b> {payment_terms}",
                    styles["Normal"]
                ),
                Paragraph(
                    f"<b>Delivery Terms:</b> {delivery_terms}",
                    styles["Normal"]
                ),
                Spacer(1, 16),
                Paragraph(
                    "<b>Note:</b> This invoice is generated from "
                    "the information entered by the user. Verify "
                    "GSTIN, HSN/SAC, applicable GST rate and other "
                    "legal invoice requirements before issuing it.",
                    styles["Normal"]
                )
            ]

            doc.build(story)
            buffer.seek(0)

            st.success(
                f"GST Bill created. Grand Total: ₹{grand_total:,.2f}"
            )

            st.download_button(
                "⬇️ Download GST Bill PDF",
                buffer,
                file_name=f"Bizly_GST_Bill_{invoice_number}.pdf",
                mime="application/pdf",
                use_container_width=True
            )

# =========================================================
# EXPORT HELP
# =========================================================

elif st.session_state.page == "Export Help":

    st.title("🌍 Export Help")

    question = st.text_area(
        "What do you want help with?",
        value=(
            "Help me understand export procedures and requirements."
        ),
        height=170
    )

    if st.button(
        "🌍 Get Export Help",
        type="primary",
        use_container_width=True
    ):
        try:
            with st.spinner("Preparing export guidance..."):
                answer = run_prompt(
                    question
                    + """
Give practical, concise guidance.
Clearly separate general information from requirements
that should be verified with official Indian authorities.
"""
                )

            st.markdown(answer)
            st.session_state.history.append(question)

        except Exception as error:
            show_ollama_error(error)

# =========================================================
# END
# =========================================================
