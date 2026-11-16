from datetime import datetime
import numpy as np, pandas as pd
from sklearn.cluster import KMeans
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_recall_fscore_support, silhouette_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from .db import conn

FEATS = ["frequency", "recency", "tenure"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
LABELS = {2: ["Jarang", "Rajin"], 3: ["Jarang", "Sedang", "Rajin"], 4: ["Tidak Aktif", "Jarang", "Sedang", "Rajin"]}

def _q(sql):
    with conn() as c:
        return pd.read_sql_query(sql, c)

def kpis():
    today = datetime.now().strftime("%Y-%m-%d")
    r = _q(f"""SELECT
      (SELECT COALESCE(SUM(amount),0) FROM transactions WHERE status='paid') AS revenue,
      (SELECT COALESCE(SUM(amount),0) FROM transactions WHERE status='paid' AND paid_at LIKE '{today}%') AS revenue_today,
      (SELECT COUNT(*) FROM users WHERE role='member' AND active_until>=datetime('now','localtime')) AS active_members,
      (SELECT COUNT(*) FROM attendance a JOIN users u ON u.id=a.user_id
       WHERE u.role='member' AND a.result='GRANTED' AND a.ts LIKE '{today}%') AS visits_today""")
    return r.iloc[0].to_dict()

def revenue_daily():
    return _q("SELECT substr(paid_at,1,10) AS date, SUM(amount) AS revenue FROM transactions "
              "WHERE status='paid' GROUP BY 1 ORDER BY 1")

def busiest():
    d = _q("SELECT a.ts FROM attendance a JOIN users u ON u.id=a.user_id WHERE u.role='member' AND a.result='GRANTED'")
    if d.empty:
        return None
    t = pd.to_datetime(d["ts"])
    return pd.crosstab(t.dt.day_name(), t.dt.hour).reindex(index=DAYS, columns=range(24), fill_value=0).fillna(0)

def features(ref_now=None):
    ref_now = pd.Timestamp(ref_now or datetime.now())
    u = _q("SELECT id,name,created_at,active_until FROM users WHERE role='member' AND active_until IS NOT NULL")
    a = _q("SELECT user_id,ts FROM attendance WHERE result='GRANTED'")
    a["ts"] = pd.to_datetime(a["ts"])
    rows = []
    for r in u.itertuples():
        end = pd.to_datetime(r.active_until)
        ref = min(ref_now, end)  # fitur dihitung sampai akhir masa aktif untuk member yang sudah berhenti
        v = a[(a.user_id == r.id) & (a.ts <= ref)]
        rec = (ref - v.ts.max()).days if len(v) else 60
        rows.append(dict(id=r.id, name=r.name,
                         frequency=int((v.ts > ref - pd.Timedelta(days=30)).sum()),
                         recency=min(rec, 60), tenure=(ref - pd.to_datetime(r.created_at)).days,
                         churn=int(end < ref_now)))
    return pd.DataFrame(rows, columns=["id", "name", *FEATS, "churn"])

def clusters(df):
    if len(df) < 8:
        return None, None
    X = StandardScaler().fit_transform(df[FEATS])
    best = None
    for k in (2, 3, 4):
        m = KMeans(k, n_init=10, random_state=42).fit(X)
        s = silhouette_score(X, m.labels_)
        if best is None or s > best[0]:
            best = (s, k, m)
    s, k, m = best
    order = df.groupby(m.labels_)["frequency"].mean().sort_values().index.tolist()
    names = {c: LABELS[k][i] for i, c in enumerate(order)}
    return df.assign(cluster=[names[c] for c in m.labels_]), round(float(s), 3)

def churn_model(df, thr=0.6):
    if len(df) < 30 or df.churn.nunique() < 2 or df.churn.value_counts().min() < 8:
        return None, None
    X, y = df[FEATS], df.churn
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.3, stratify=y, random_state=42)
    models = {"Logistic Regression": make_pipeline(StandardScaler(), LogisticRegression(class_weight="balanced", max_iter=1000)),
              "Random Forest": RandomForestClassifier(200, class_weight="balanced", random_state=42)}
    rows = []
    for n, m in models.items():
        m.fit(Xtr, ytr)
        p, r, f, _ = precision_recall_fscore_support(yte, m.predict(Xte), average="binary", zero_division=0)
        rows.append(dict(model=n, precision=p, recall=r, f1=f))
    act = df[df.churn == 0].copy()
    act["churn_prob"] = models["Logistic Regression"].predict_proba(act[FEATS])[:, 1]
    act["at_risk"] = act.churn_prob >= thr
    return pd.DataFrame(rows).round(3), act.sort_values("churn_prob", ascending=False)
