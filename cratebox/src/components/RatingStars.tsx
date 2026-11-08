import { Star } from "lucide-react";

interface RatingStarsProps {
  rating: number;
  onChange: (rating: number) => void;
  disabled?: boolean;
}

export function RatingStars({ rating, onChange, disabled = false }: RatingStarsProps) {
  return (
    <span className="flex gap-0.5" role="group" aria-label="Rate loaded track">
      {[1, 2, 3, 4, 5].map((star) => (
        <button
          key={star}
          type="button"
          disabled={disabled}
          aria-label={`Set rating to ${star} stars`}
          aria-pressed={rating === star}
          title={rating === star ? "Clear rating" : `Rate ${star} stars`}
          onClick={() => onChange(rating === star ? 0 : star)}
          className="rounded-sm p-0.5 text-muted-foreground hover:text-gold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-wait disabled:opacity-50"
        >
          <Star
            size={14}
            className={star <= rating ? "fill-gold text-gold" : ""}
            aria-hidden="true"
          />
        </button>
      ))}
    </span>
  );
}
