/** @jsxImportSource preact */
import {useEffect,useRef,useState} from 'preact/hooks';
import {reviewProductId, secondProductImage, REVIEW_IMAGE_QUERY} from './account-review-utils.js';
import {fileFromDropEvent,inputValue,isAllowedReviewPhoto} from './vault-utils.js';
export function AccountReview({prompt, certificate, request, api}) {
  const [submitted,setSubmitted]=useState(false);
  const onSubmitted=()=>setSubmitted(true);
  const [rating, setRating] = useState(0);
  const [name, setName] = useState("");
  const [setupImage, setSetupImage] = useState(null);
  const productId = reviewProductId(prompt, certificate);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [photo, setPhoto] = useState(null);
  const [photoError, setPhotoError] = useState("");
  const [submitState, setSubmitState] = useState({status: "idle", message: ""});
  const modalId = "collector-review-modal";
  const readerRef = useRef(null);
  const modalRef = useRef(null);

  useEffect(() => {

    return () => {
      if (readerRef.current?.readyState === 1) readerRef.current.abort();
    };
  }, []);

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
    const file = fileFromDropEvent(event);
    const validation = isAllowedReviewPhoto(file);
    if (!validation.ok) {
      setPhoto(null);
      setPhotoError(validation.error);
      return;
    }
    const reader = new FileReader();
    readerRef.current = reader;
    reader.onload = () => {
      const dataUrl = String(reader.result || "");
      setPhoto({
        name: file.name,
        mime_type: file.type,
        size: file.size,
        base64: dataUrl.split(",", 2)[1] || "",
        preview: dataUrl,
      });
      setPhotoError("");
      };
    reader.onerror = () => setPhotoError("Photo could not be read.");
    reader.readAsDataURL(file);
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
      await request("/api/collector-vault/review", {
        method: "POST",
        body: {
          review_reference: prompt.reference,
          rating,
          reviewer_name: name.trim(),
          title,
          body,
          photo: photo ? {
            mime_type: photo.mime_type,
            filename: photo.name,
            base64: photo.base64,
          } : null,
        },
      });
      setSubmitState({status: "submitted", message: "Review submitted ✓"});
      onSubmitted();
    } catch (error) {
      setSubmitState({status: "error", message: "Your review could not be submitted. Please try again."});
    }
  };

  return (
    <s-box padding="none" border="base" borderRadius="large" overflow="hidden" background="subdued">
      <s-grid gridTemplateColumns="@container (inline-size > 650px) '144px minmax(0, 1fr)', '76px minmax(0, 1fr)'" gap="small" alignItems="center">
        <s-box>
          <s-box display="@container (inline-size > 650px) auto, none"><s-image src={certificate?.purchased_image_url || certificate?.certificate_preview_image_url} alt={certificate?.purchased_image_alt || "Your collection"} aspectRatio="1.5" objectFit="cover" loading="eager" /></s-box>
          <s-box display="@container (inline-size > 650px) none, auto"><s-image src={certificate?.purchased_image_url || certificate?.certificate_preview_image_url} alt={certificate?.purchased_image_alt || "Your collection"} aspectRatio="0.75" objectFit="cover" loading="eager" /></s-box>
        </s-box>
        <s-box padding="small">
          <s-grid gridTemplateColumns="@container (inline-size > 650px) 'minmax(0, 1fr) 164px', 'minmax(0, 1fr) 88px'" gap="small" alignItems="center">
            <s-stack gap="small-400">
              <s-text type="strong">{submitted ? "Thank you for your review" : "How does it look in your space?"}</s-text>
              <StarRating rating={rating || 5} onChange={chooseRating} modalId={modalId} compact />
            </s-stack>
            <s-button inlineSize="fill" variant="primary" command="--show" commandFor={modalId} onClick={()=>chooseRating(rating || 5)}>Leave a review</s-button>
          </s-grid>
        </s-box>
      </s-grid>
      <s-modal
        ref={modalRef}
        id={modalId}
        heading="How does it look in your space?"
        accessibilityLabel={`Leave a review for ${prompt?.product_title || certificate?.product_title || "your edition"}`}
        size="large"
      >
        <s-stack gap="small">
          {!prompt ? <s-banner tone="info">Reviews are available for delivered editions. Your review options will appear here when ready.</s-banner> : null}
          <s-grid gridTemplateColumns="80px minmax(0, 1fr)" gap="base" alignItems="center">
            <s-image src={certificate?.purchased_image_url || certificate?.certificate_preview_image_url} alt={certificate?.purchased_image_alt || "Your edition"} aspectRatio="4/3" objectFit="cover" />
            <s-stack gap="small-400">
              <s-text type="strong">{prompt?.product_title || certificate?.product_title}</s-text>
              <s-text color="subdued">Edition {certificate?.edition_display?.replace(/^#/, "").replace(/\s*\/\s*/, " of ")}</s-text>
            </s-stack>
          </s-grid>
          <s-divider />
          <s-text type="strong">Your rating</s-text>
          <StarRating rating={rating} onChange={chooseRating} />
          <s-box border="base" borderRadius="large" padding="base" background="subdued">
            <s-grid gridTemplateColumns="@container (inline-size > 500px) 'minmax(0, 1fr) minmax(0, 1.2fr)', 'minmax(0, 1fr)'" gap="base" alignItems="center">
              <s-image src={setupImage?.url || certificate?.purchased_image_url} alt={setupImage?.altText || "Your edition in a room"} aspectRatio="1.25" objectFit="cover" loading="lazy" />
              <s-stack gap="small">
                <s-heading>Show us your setup</s-heading>
                <s-text>Start with the whole wall, then move in on your edition number.</s-text>
                <s-drop-zone
                  label="Add photo (optional)"
                  accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"
                  error={photoError}
                  onInput={handlePhoto}
                ></s-drop-zone>
              </s-stack>
            </s-grid>
          </s-box>
          <s-text-field label="Name" value={name} maxLength={120} required
            onInput={(event) => setName(inputValue(event))}></s-text-field>
          <s-text-field label="Review title (optional)" value={title} maxLength={120}
            onInput={(event) => setTitle(inputValue(event))}></s-text-field>
          <s-text-area label="Your review" placeholder="What stands out now that it’s on your wall?"
            value={body} minLength={10} maxLength={2000} required rows={3}
            onInput={(event) => setBody(inputValue(event))}></s-text-area>
          {photo ? (
            <s-stack gap="small">
              <s-image
                src={photo.preview}
                alt={`Selected review photo ${photo.name}`}
                aspectRatio="16/9"
                objectFit="contain"
              ></s-image>
              <s-stack direction="inline" gap="small" alignItems="center">
                <s-text>{photo.name}</s-text>
                <s-button onClick={() => setPhoto(null)}>Remove photo</s-button>
              </s-stack>
            </s-stack>
          ) : null}
          {submitState.message ? (
            <s-banner tone={submitState.status === "error" ? "critical" : "success"}>
              {submitState.message}
            </s-banner>
          ) : null}
        </s-stack>
        <s-button
          slot="primary-action"
          variant="primary"
          onClick={submitReview}
          disabled={!prompt || submitted}
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
    <s-grid gridTemplateColumns="repeat(5, minmax(0, 1fr))" inlineSize={compact ? "120px" : "260px"} gap="none" alignItems="center">
      {[1, 2, 3, 4, 5].map((value) => (
        <s-clickable
          key={value}
          accessibilityLabel={`${value} star${value === 1 ? "" : "s"}`}
          onClick={() => onChange(value)}
          command={modalId ? "--show" : undefined}
          commandFor={modalId || undefined}
          padding={compact ? "none" : "small-400"}
          minBlockSize={compact ? "28px" : "36px"}
          minInlineSize={compact ? "24px" : "36px"}
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
