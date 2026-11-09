"""
A little website to tell her how much you love her.

Run it:
    pip install flask
    python app.py
Then open http://127.0.0.1:5000

Edit the CONFIG section below, that's all the personalizing you need.
"""
from flask import Flask, render_template_string

# ---------------- CONFIG: make it yours ----------------
HER_NAME = "Her Name"
YOUR_NAME = "Your Name"
TOGETHER_SINCE = "2023-09-09T01:00:00"   # the day it started (YYYY-MM-DDTHH:MM:SS)

REASONS = [
    "The way you laugh at your own jokes before you finish them.",
    "You make ordinary Tuesdays feel like something worth remembering.",
    "You're kind to people when no one is watching.",
    "Home is wherever you are.",
    "You believe in me on the days I forget to.",
]

FINAL_MESSAGE = (
    "I don't have a perfect way to say this, so I built a website instead. "
    "Thank you for being you. I love you, today and every day after."
)
# --------------------------------------------------------

app = Flask(__name__)

PAGE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>For {{ her }}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;1,9..144,300;1,9..144,600&family=DM+Sans:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root{
    --wine:#2a0f1e; --plum:#3d1830; --petal:#f7c6d0; --blush:#fff1f3; --gold:#e8b86d;
  }
  *{box-sizing:border-box;margin:0}
  html{scroll-behavior:smooth}
  body{background:var(--wine);color:var(--blush);font-family:'DM Sans',system-ui,sans-serif;line-height:1.6;overflow-x:hidden}
  section{min-height:100vh;display:flex;flex-direction:column;justify-content:center;padding:4rem 1.5rem;max-width:44rem;margin:0 auto}
  h1,h2,.serif{font-family:'Fraunces',Georgia,serif;font-weight:300;font-style:italic;letter-spacing:-.01em}
  h1{font-size:clamp(2.8rem,10vw,5.5rem);line-height:1.05;color:var(--petal)}
  .lead{margin-top:1.2rem;color:var(--blush);opacity:.8;max-width:30rem}

  /* the memorable thing: a clock counting every second with you */
  .clock{display:flex;gap:clamp(.8rem,3vw,2rem);margin-top:2.5rem;flex-wrap:wrap}
  .unit{min-width:4.5rem}
  .unit b{display:block;font-family:'Fraunces',serif;font-weight:600;font-size:clamp(2.2rem,8vw,3.8rem);line-height:1;color:var(--gold);font-variant-numeric:tabular-nums}
  .unit span{font-size:.9rem;opacity:.7}
  .hint{margin-top:3rem;opacity:.55;font-size:.95rem}

  h2{font-size:clamp(1.8rem,5vw,2.6rem);color:var(--petal);margin-bottom:2rem}
  ul{list-style:none;padding:0}
  li{padding:1.1rem 0 1.1rem 1.4rem;border-left:2px solid var(--gold);margin-bottom:.4rem;font-size:1.1rem;
     opacity:.25;transform:translateX(-8px);transition:opacity .6s,transform .6s}
  li.seen{opacity:1;transform:none}

  button{margin-top:1.5rem;align-self:flex-start;background:var(--petal);color:var(--wine);border:0;border-radius:999px;
     padding:.9rem 1.8rem;font:500 1rem 'DM Sans',sans-serif;cursor:pointer;transition:transform .15s,background .15s}
  button:hover{transform:scale(1.04);background:#fff}
  button:focus-visible{outline:3px solid var(--gold);outline-offset:3px}

  #letter{margin-top:2.5rem;font-size:clamp(1.3rem,4vw,1.8rem);line-height:1.5;min-height:9rem}
  .sig{margin-top:1.5rem;color:var(--gold);opacity:0;transition:opacity 1s}
  .sig.show{opacity:1}

  .heart{position:fixed;bottom:-2rem;pointer-events:none;color:var(--petal);animation:rise linear forwards}
  @keyframes rise{to{transform:translateY(-110vh) rotate(25deg);opacity:0}}
  @media (prefers-reduced-motion:reduce){.heart{display:none} li{transition:none}}
</style>
</head>
<body>

<section>
  <h1>For {{ her }}.</h1>
  <p class="lead">Every second since we started, I've been a little luckier than I deserve.</p>
  <div class="clock" aria-live="off">
    <div class="unit"><b id="d">0</b><span>days</span></div>
    <div class="unit"><b id="h">0</b><span>hours</span></div>
    <div class="unit"><b id="m">0</b><span>minutes</span></div>
    <div class="unit"><b id="s">0</b><span>seconds</span></div>
  </div>
  <p class="hint">Keep scrolling.</p>
</section>

<section>
  <h2>Some of the reasons</h2>
  <ul>
    {% for r in reasons %}<li>{{ r }}</li>{% endfor %}
  </ul>
</section>

<section>
  <h2>One more thing</h2>
  <button id="open">Open this</button>
  <p id="letter" class="serif" aria-live="polite"></p>
  <p class="sig serif" id="sig">Forever yours, {{ you }}</p>
</section>

<script>
  // Live counter
  const start = new Date("{{ since }}").getTime();
  const pad = n => String(n);
  function tick(){
    let t = Math.max(0, Math.floor((Date.now() - start) / 1000));
    document.getElementById('d').textContent = pad(Math.floor(t / 86400));
    document.getElementById('h').textContent = pad(Math.floor(t % 86400 / 3600));
    document.getElementById('m').textContent = pad(Math.floor(t % 3600 / 60));
    document.getElementById('s').textContent = pad(t % 60);
  }
  tick(); setInterval(tick, 1000);

  // Reasons fade in as you scroll to them
  const io = new IntersectionObserver(es => es.forEach(e => e.isIntersecting && e.target.classList.add('seen')),
                                      {threshold: .6});
  document.querySelectorAll('li').forEach(li => io.observe(li));

  // The letter types itself out, with hearts
  const message = {{ message|tojson }};
  const btn = document.getElementById('open');
  btn.addEventListener('click', () => {
    btn.disabled = true; btn.style.display = 'none';
    const out = document.getElementById('letter'); let i = 0;
    const type = setInterval(() => {
      out.textContent = message.slice(0, ++i);
      if (i >= message.length){ clearInterval(type); document.getElementById('sig').classList.add('show'); }
    }, 45);
    for (let k = 0; k < 24; k++) setTimeout(heart, k * 180);
  });
  function heart(){
    const h = document.createElement('div');
    h.className = 'heart'; h.textContent = '\\u2665';
    h.style.left = Math.random() * 95 + 'vw';
    h.style.fontSize = (1 + Math.random() * 1.8) + 'rem';
    h.style.animationDuration = (4 + Math.random() * 4) + 's';
    document.body.appendChild(h);
    setTimeout(() => h.remove(), 8500);
  }
</script>
</body>
</html>
"""


@app.route("/")
def home():
    return render_template_string(
        PAGE, her=HER_NAME, you=YOUR_NAME, since=TOGETHER_SINCE,
        reasons=REASONS, message=FINAL_MESSAGE,
    )


if __name__ == "__main__":
    app.run(debug=True)