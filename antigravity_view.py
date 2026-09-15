import json
import streamlit as st
import streamlit.components.v1 as components


def render_antigravity_dashboard(df):
  st.markdown("### 🌀 Antigravity Interactive Zones")
  st.caption(
      "Przeciągaj kafelki stref myszką. Ich rozmiar odzwierciedla zużycie"
      " energii w kWh."
  )

  zone_data = []
  colors = {
      "Salon": "#FF5722",
      "Sypialnia": "#2196F3",
      "Pokój Dziecięcy": "#4CAF50",
      "Kuchnia": "#FFC107",
  }

  if (
      df is not None
      and not df.empty
      and "zone" in df.columns
      and "delta_units" in df.columns
  ):
    summary = df.groupby("zone")["delta_units"].sum().reset_index()
    for _, row in summary.iterrows():
      z_name = str(row["zone"])
      val = float(row["delta_units"]) if row["delta_units"] > 0 else 10.0
      zone_data.append(
          {"name": z_name, "val": val, "color": colors.get(z_name, "#9C27B0")}
      )
  else:
    zone_data = [
        {"name": "Salon", "val": 45.5, "color": "#FF5722"},
        {"name": "Sypialnia", "val": 28.0, "color": "#2196F3"},
        {"name": "Pokój Dziecięcy", "val": 32.1, "color": "#4CAF50"},
    ]

  zones_json = json.dumps(zone_data)

  html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/matter-js/0.19.0/matter.min.js"></script>
        <style>
            body {{ margin: 0; padding: 0; overflow: hidden; background: transparent; font-family: sans-serif; }}
            canvas {{ width: 100%; height: 420px; display: block; border-radius: 12px; }}
        </style>
    </head>
    <body>
        <script>
            const zones = {zones_json};

            let Engine = Matter.Engine,
                Render = Matter.Render,
                Runner = Matter.Runner,
                Bodies = Matter.Bodies,
                Composite = Matter.Composite,
                Mouse = Matter.Mouse,
                MouseConstraint = Matter.MouseConstraint;

            let engine = Engine.create();
            
            let render = Render.create({{
                element: document.body,
                engine: engine,
                options: {{
                    width: 800,
                    height: 400,
                    wireframes: false,
                    background: '#1e1e2e'
                }}
            }});

            Render.run(render);
            let runner = Runner.create();
            Runner.run(runner, engine);

            Composite.add(engine.world, [
                Bodies.rectangle(400, 410, 810, 30, {{ isStatic: true, render: {{ fillStyle: '#313244' }} }}),
                Bodies.rectangle(-10, 200, 30, 400, {{ isStatic: true }}),
                Bodies.rectangle(810, 200, 30, 400, {{ isStatic: true }})
            ]);

            let xPos = 150;
            zones.forEach((z) => {{
                let size = Math.min(Math.max(z.val * 3, 80), 180);
                let box = Bodies.rectangle(xPos, 50, size, 60, {{
                    chamfer: {{ radius: 8 }},
                    density: 0.005,
                    restitution: 0.6,
                    render: {{
                        fillStyle: z.color,
                        strokeStyle: '#ffffff',
                        lineWidth: 2
                    }}
                }});
                Composite.add(engine.world, box);
                xPos += 220;
            }});

            let mouse = Mouse.create(render.canvas);
            let mouseConstraint = MouseConstraint.create(engine, {{
                mouse: mouse,
                constraint: {{
                    stiffness: 0.2,
                    render: {{ visible: true, strokeStyle: '#f5e0dc' }}
                }}
            }});
            Composite.add(engine.world, mouseConstraint);
        </script>
    </body>
    </html>
    """
  components.html(html_code, height=430)
