import { VideoPlayer as ModularVideoPlayer } from "./media/VideoPlayer";

export default function VideoPlayer(props: {
  youtubeVideoId?: string;
  videoId?: string;
  provider?: string | null;
  playbackUrl?: string | null;
  title: string;
  onPrev?: () => void;
  onNext?: () => void;
  hasPrev?: boolean;
  hasNext?: boolean;
}) {
  return (
    <ModularVideoPlayer
      videoId={props.videoId || props.youtubeVideoId || ""}
      provider={props.provider}
      playbackUrl={props.playbackUrl}
      title={props.title}
      onPrev={props.onPrev}
      onNext={props.onNext}
      hasPrev={props.hasPrev}
      hasNext={props.hasNext}
    />
  );
}

export { ModularVideoPlayer as VideoPlayer };
