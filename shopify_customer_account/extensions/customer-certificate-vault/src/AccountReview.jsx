/** @jsxImportSource preact */
import {useEffect,useRef,useState} from 'preact/hooks';
import {fileFromDropEvent,inputValue,isAllowedReviewPhoto} from './vault-utils.js';
export function AccountReview({prompt, certificate, request}) {
  const [submitted,setSubmitted]=useState(false);
  const onSubmitted=()=>setSubmitted(true);
  const [rating, setRating] = useState(0);
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
    <s-box padding="small" border="base" borderRadius="base" background="subdued">
      <s-grid gridTemplateColumns="@container (inline-size > 650px) 56px minmax(0, 1fr) auto, 44px minmax(0, 1fr)" gap="small" alignItems="center">
        <s-image src={certificate?.purchased_image_url || certificate?.certificate_preview_image_url}
          alt={certificate?.purchased_image_alt || "Your collection"} aspectRatio="1/1" objectFit="contain" loading="lazy" />
        <s-stack gap="small-400">
          <s-text type="strong">{submitted ? "Thank you for your review" : "How does it look in your space?"}</s-text>
          <StarRating rating={rating} onChange={chooseRating} modalId={modalId} />
        </s-stack>
        <s-button command="--show" commandFor={modalId} onClick={()=>chooseRating(rating || 5)}>Leave a review</s-button>
      </s-grid>
      <s-modal
        ref={modalRef}
        id={modalId}
        heading={`Review ${prompt?.product_title || certificate?.product_title || "your edition"}`}
        accessibilityLabel={`Leave a review for ${prompt?.product_title || certificate?.product_title || "your edition"}`}
        size="large"
      >
        <s-stack gap="small">
          {!prompt ? <s-banner tone="info">Reviews are available for delivered editions. Your review options will appear here when ready.</s-banner> : null}
          <s-text color="subdued">Your review is sent to Judge.me, just like the store reviews page.</s-text>
          <StarRating rating={rating} onChange={chooseRating} />
          <s-text-field
            label="Review title (optional)"
            value={title}
            maxLength={120}
            onInput={(event) => setTitle(inputValue(event))}
          ></s-text-field>
          <s-text-area
            label="Your review"
            value={body}
            minLength={10}
            maxLength={2000}
            required
            rows={3}
            onInput={(event) => setBody(inputValue(event))}
          ></s-text-area>
          <s-drop-zone
            label="Add a customer photo (optional)"
            accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"
            error={photoError}
                onInput={handlePhoto}
          ></s-drop-zone>
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

function StarRating({rating, onChange, modalId = ""}) {
  return (
    <s-stack direction="inline" gap="none" alignItems="center">
      {[1, 2, 3, 4, 5].map((value) => (
        <s-clickable
          key={value}
          accessibilityLabel={`${value} star${value === 1 ? "" : "s"}`}
          onClick={() => onChange(value)}
          command={modalId ? "--show" : undefined}
          commandFor={modalId || undefined}
          padding="small-400"
          minBlockSize="36px"
          minInlineSize="36px"
        >
          <s-icon
            type={value <= rating ? "star-filled" : "star"}
            tone={value <= rating ? "warning" : "neutral"}
          ></s-icon>
        </s-clickable>
      ))}
    </s-stack>
  );
}

