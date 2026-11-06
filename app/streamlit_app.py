"""Policy Evidence & Intelligence dashboard. Run: streamlit run app/streamlit_app.py"""

import streamlit as st

st.set_page_config(page_title="Policy Evidence & Intelligence", layout="wide")

pages = [
    st.Page("views/overview.py", title="Overview", default=True),
    st.Page("views/intelligence.py", title="Intelligence"),
    st.Page("views/members.py", title="Members"),
    st.Page("views/metrics.py", title="Metrics registry"),
    st.Page("views/flagship.py", title="Flagship study"),
    st.Page("views/methods.py", title="Methods & evaluation"),
]
st.navigation(pages).run()
