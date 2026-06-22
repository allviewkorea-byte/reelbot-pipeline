import { Composition } from "remotion";
import { MusicViz, MusicVizProps } from "./MusicViz";

const FPS = 30;

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="MusicViz"
      component={MusicViz}
      fps={FPS}
      width={1920}
      height={1080}
      durationInFrames={300}
      defaultProps={{ tracks: [], mood: "", durationSec: 10, vizSpec: null } as MusicVizProps}
      // 실제 길이는 props.durationSec(믹스 길이)로 결정.
      calculateMetadata={({ props }) => ({
        durationInFrames: Math.max(30, Math.round((props.durationSec || 10) * FPS)),
      })}
    />
  );
};
