# Sports Cave Image Factory

Streamlit tool for Sports Cave staff to upload one finished artwork and generate:

- Black framed WebP
- Oak framed WebP
- White framed WebP
- Unframed WebP
- Size guide WebP
- Black framed JPG
- Oak framed JPG
- White framed JPG
- Unframed JPG
- Size guide JPG
- Review PNG previews
- Shopify Pack ZIP in WebP
- Social Media Pack ZIP in JPG
- ChatGPT lifestyle prompt pack ZIP
- Complete production pack ZIP

## Local Run

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Start the app:

```bash
python -m streamlit run app.py
```

You can also use `start-app.bat` on Windows.

## Render Deployment

This repo includes:

- `render.yaml`
- `runtime.txt`
- `.streamlit/config.toml`

Deploy steps:

1. Push this project to GitHub.
2. In Render, create a new Web Service from the GitHub repo.
3. Let Render read `render.yaml`.
4. Deploy the service.

The service will start with:

```bash
python -m streamlit run app.py --server.address 0.0.0.0 --server.port $PORT --server.headless true
```

## VA Usage

1. Open the private app URL.
2. Upload the finished artwork file.
3. Confirm or edit the auto-filled product name.
4. Choose the sport category.
5. Click `Generate Images`.
6. Review the preview images.
7. Download the Shopify Pack in WebP, the Social Media Pack in JPG, the complete production pack ZIP, or the lifestyle prompt ZIP.
8. Use the black framed ChatGPT reference image with the included SOP prompts.

The app stores each run in `output/runs/...` when running locally. On hosted platforms like Render, those files are temporary unless persistent storage is added.

## ChatGPT Lifestyle Prompt Workflow

The app now prepares the manual ChatGPT lifestyle workflow for you:

- It generates the core Shopify product images.
- It copies the black framed WebP into the run as the ChatGPT reference image.
- It creates the SOP lifestyle prompt text files.
- It creates a lifestyle prompt ZIP with the reference image and prompts.
- It creates a complete production pack ZIP that includes the Shopify WebP pack, the Social Media JPG pack, and the ChatGPT prompt assets.
- It lets the VA upload the finished ChatGPT lifestyle images back into the same run.
- It saves those returned lifestyle images into both the `webp` and `jpg` folders with SEO-style filenames.
- It refreshes the complete production pack ZIP to include whatever lifestyle images have been added so far.

This workflow does not use the OpenAI API.
This workflow does not automate the ChatGPT website.
The actual lifestyle mockup images are still created manually in ChatGPT.

Recommended VA flow:

1. Download the black framed ChatGPT reference image or the complete production pack ZIP.
2. Open ChatGPT.
3. Upload the black framed reference image.
4. Use Prompt 01 first.
5. Keep Prompts 02 and 03 in the same chat if you want ChatGPT to continue from the last generated image.
6. Use Prompts 04 to 09 one at a time.
7. Upload or paste each finished lifestyle mockup back into its matching prompt section in the app.
8. Download the refreshed Shopify Pack, Social Media Pack, or complete production pack ZIP when you are done.

## Testing The Hosted App

1. Open the Render URL after deployment finishes.
2. Upload a sample artwork.
3. Confirm previews render and all ZIP download buttons work.
4. Confirm the black framed ChatGPT reference file downloads correctly.
5. Open one of the prompt expanders and confirm the SOP text is visible.
6. Run a second job to confirm each run gets its own timestamped output folder logic.
