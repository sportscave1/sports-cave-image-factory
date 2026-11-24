/** @jsxImportSource preact */
import {collectionThumbnail} from './collection-image-utils.js';
import {useEffect,useRef,useState} from 'preact/hooks';
import {reviewProductId, secondProductImage, REVIEW_IMAGE_QUERY} from './account-review-utils.js';
import {inputValue} from './vault-utils.js';
export function AccountReview({prompt, certificate, request, api, reviewStatus = "ready", onRetryReview = () => {}}) {
  const [submitted,setSubmitted]=useState(false);
  const onSubmitted=()=>setSubmitted(true);
  const [rating, setRating] = useState(5);
  const [name, setName] = useState("");
  const [setupImage, setSetupImage] = useState(null);
  const productId = reviewProductId(prompt, certificate);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [files,setFiles]=useState([]);
  const [photoError, setPhotoError] = useState("");
  const [submitState, setSubmitState] = useState({status: "idle", message: ""});
  const modalId = "collector-review-modal";
  const [previews,setPreviews]=useState({});
  const modalRef = useRef(null);

  useEffect(() => {
    let active=true;const readers=[];setPreviews({});
    files.forEach((file,index)=>{
      if(!file.type.startsWith('image/') || file.size>5*1024*1024)return;
      const reader=new FileReader();readers.push(reader);
      reader.onload=()=>{if(active)setPreviews(value=>({...value,[index]:String(reader.result || '')}));};
      reader.readAsDataURL(file);
    });
    return ()=>{active=false;readers.forEach(reader=>{if(reader.readyState===1)reader.abort();});};
  },[files]);

  useEffect(() => {
    let active = true;
    setSetupImage(null);
    if (productId) api.query(REVIEW_IMAGE_QUERY, {variables: {id: productId}})
      .then(result => { if (active) setSetupImage(secondProductImage(result.data?.product)); })
      .catch(() => {}); // Purchased image remains usable when product media is unavailable.
    return () => { active = false; };
  }, [api, productId]);

  const chooseRating = (value) => {
    setRating(value);
  };

  const handlePhoto = (event) => {
    const selected=Array.from(event?.files || event?.detail?.files || event?.currentTarget?.files || event?.target?.files || []);
    if(selected.length>5 || selected.filter(f=>f.type.startsWith('video/')).length>1 || selected.some(f=>f.size>(f.type.startsWith('video/')?150:25)*1024*1024) || selected.reduce((n,f)=>n+f.size,0)>250*1024*1024){setPhotoError('Choose up to five files, including one video. A selected file is too large.');return;}
    setPhotoError('');setFiles(selected);
  };

  const submitReview = async () => {
    if (!rating) {
      setSubmitState({status: "error", message: "Choose a star rating."});
      return;
    }
    if (!name.trim()) {
      setSubmitState({status: "error", message: "Enter your name."});
      return;
    }
    if (body.trim().length < 10) {
      setSubmitState({status: "error", message: "Review text must be at least 10 characters."});
      return;
    }
    setSubmitState({status: "submitting", message: ""});
    try {
      const data=new FormData();
      for(const [key,value] of Object.entries({review_reference:prompt.reference,rating:String(rating),reviewer_name:name.trim(),title,body,display_consent:'yes'}))data.append(key,value);
      for(const file of files)data.append('media',file,file.name);
      await request('/api/collector-vault/review',{method:'POST',body:data});
      setSubmitState({status: "submitted", message: "Review submitted ✓"});
      onSubmitted();
    } catch (error) {
      setSubmitState({status: "error", message: "Your review could not be submitted. Please try again."});
    }
  };

  return (
    <s-box padding="none" border="base" borderRadius="large" overflow="hidden" background="subdued">
      <s-grid gridTemplateColumns="@container (inline-size > 650px) '144px minmax(0, 1fr)', 'minmax(0, 1fr)'" gap="small" alignItems="center">
        <s-box display="@container (inline-size > 650px) auto, none">
          <s-box><s-image src={collectionThumbnail(certificate?.purchased_image_url) || certificate?.certificate_preview_image_url} alt={certificate?.purchased_image_alt || "Your collection"} aspectRatio="1.5" objectFit="cover" loading="eager" /></s-box>
        </s-box>
        <s-box padding="small">
          <s-grid gridTemplateColumns="@container (inline-size > 650px) 'minmax(0, 1fr) 164px', 'minmax(0, 1fr) 128px'" gap="small" alignItems="center">
            <s-stack gap="small-400">
              <s-text type="strong">{submitted ? "Thank you for your review" : "How does it look in your space?"}</s-text>
              <StarRating rating={rating || 5} onChange={chooseRating} modalId={modalId} compact />
            </s-stack>
            {reviewStatus === "error" ? <s-button inlineSize="fill" variant="primary" onClick={onRetryReview}>Retry review</s-button> :
              <s-button inlineSize="fill" variant="primary" command="--show" commandFor={modalId} onClick={()=>chooseRating(rating || 5)}>Leave a review</s-button>}

          </s-grid>
        </s-box>
      </s-grid>
      <s-modal
        ref={modalRef}
        id={modalId}
        heading="Leave a review"
        accessibilityLabel={`Leave a review for ${prompt?.product_title || certificate?.product_title || "your edition"}`}
        size="max"
        padding="none"
      >
        <s-query-container>
        <s-grid gridTemplateColumns="minmax(0, 1000px)" justifyContent="center" paddingInline="small" paddingBlock="none">
          {reviewStatus === "error" ? <s-banner tone="critical">Review options could not load. Please try again.<s-button onClick={onRetryReview}>Retry review</s-button></s-banner> : reviewStatus === "loading" ? <s-banner tone="info">Loading your review options…</s-banner> : !prompt ? <s-banner tone="info">There are no editions awaiting a review.</s-banner> : null}
        <s-grid gridTemplateColumns="@container (inline-size > 500px) 'minmax(0, 1.15fr) minmax(0, 1fr)', 'minmax(0, 1fr)'" gap="small-400" alignItems="start" maxInlineSize="1000px">
        <s-stack gap="none">
          <s-text type="strong">{prompt?.product_title || certificate?.product_title}</s-text>
          <s-grid gridTemplateColumns="minmax(0, 1fr) 220px" gap="small" alignItems="center">
            <s-text>Your rating</s-text>
            <StarRating rating={rating} onChange={chooseRating} />
          </s-grid>
          <s-grid gridTemplateColumns="repeat(2, minmax(0, 1fr))" gap="small">
            <s-text-field label="Name" value={name} maxLength={120} required
              onInput={(event) => setName(inputValue(event))}></s-text-field>
            <s-text-field label="Review title (optional)" value={title} maxLength={120}
              onInput={(event) => setTitle(inputValue(event))}></s-text-field>
          </s-grid>
          <s-text-area label="Your review"
            value={body} minLength={10} maxLength={2000} required rows={1}
            onInput={(event) => setBody(inputValue(event))}></s-text-area>
          {submitState.message ? (
            <s-banner tone={submitState.status === "error" ? "critical" : "success"}>
              {submitState.message}
            </s-banner>
          ) : null}
        </s-stack>
          <s-stack gap="none">
          <s-stack gap="none">
            <s-text type="strong">Show us your setup</s-text>
            <s-text type="small" color="subdued">Start with your wall, then your edition number.</s-text>
          </s-stack>
            <s-grid gridTemplateColumns="minmax(0, 1fr) 100px" gap="small" alignItems="center">
              <s-box inlineSize="100%" maxInlineSize="320px">
                <s-image src={setupImage?.url || collectionThumbnail(certificate?.purchased_image_url, 480)} alt={setupImage?.altText || "Your edition in a room"} inlineSize="fill" aspectRatio="1" objectFit="contain" loading="lazy" borderRadius="base" />
              </s-box>
            {files.length ? <s-stack gap="small-400">
              <s-stack gap="none">
                {files.map((file,index)=><s-grid key={index} gridTemplateColumns="24px minmax(0, 1fr) 24px" gap="small-400" alignItems="center">
                  <s-box inlineSize="24px" blockSize="24px">{previews[index]?<s-image src={previews[index]} alt={`Selected review photo ${file.name}`} aspectRatio="1" objectFit="contain" />:<s-text type="small">{file.type.startsWith('video/')?'▶':'▧'}</s-text>}</s-box>
                  <s-text type="small">{file.name.length>9?file.name.slice(0,6)+'…':file.name}</s-text>
                  <s-clickable accessibilityLabel={`Remove ${file.name}`} minBlockSize="24px" minInlineSize="24px" padding="none" onClick={()=>setFiles(files.filter((_,i)=>i!==index))}>×</s-clickable>
                </s-grid>)}
              </s-stack>
              <s-clickable accessibilityLabel="Change photo/video" minBlockSize="28px" padding="none" onClick={()=>setFiles([])}><s-text type="small">Change files</s-text></s-clickable>
            </s-stack> : <s-stack gap="small-400">
              <s-box display="@container (inline-size > 500px) none, auto"><s-text type="small">Add photo/video (optional)</s-text></s-box>
              <s-box inlineSize="100px">
              <s-drop-zone
              accessibilityLabel="Add photo/video (optional)"
              multiple
              accept="image/jpeg,image/png,image/webp,video/mp4,video/webm"
              error={photoError}
              onInput={handlePhoto}
            ></s-drop-zone>
              </s-box>
            </s-stack>}
            </s-grid>
          </s-stack>
        </s-grid>
        </s-grid>
        </s-query-container>
        <s-button
          slot="primary-action"
          variant="primary"
          onClick={submitReview}
          disabled={!prompt || submitted || submitState.status === "submitting"}
          loading={submitState.status === "submitting"}
        >
          Submit review
        </s-button>
        <s-button slot="secondary-actions" command="--hide" commandFor={modalId}>
          Cancel
        </s-button>
      </s-modal>
    </s-box>
  );
}

function StarRating({rating, onChange, modalId = "", compact = false}) {
  return (
    <s-grid gridTemplateColumns="repeat(5, minmax(0, 1fr))" inlineSize={compact ? "120px" : "220px"} gap="none" alignItems="center">
      {[1, 2, 3, 4, 5].map((value) => (
        <s-clickable
          key={value}
          accessibilityLabel={`${value} star${value === 1 ? "" : "s"}`}
          onClick={() => onChange(value)}
          command={modalId ? "--show" : undefined}
          commandFor={modalId || undefined}
          padding={compact ? "none" : "small-400"}
          minBlockSize={compact ? "28px" : "40px"}
          minInlineSize={compact ? "24px" : "44px"}
        >
          <s-icon
            type={value <= rating ? "star-filled" : "star"}
            tone="warning"
            size={compact ? "base" : "large"}
          ></s-icon>
        </s-clickable>
      ))}
    </s-grid>
  );
}
