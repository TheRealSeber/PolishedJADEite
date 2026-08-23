import java.util.ArrayList;
import java.util.List;
import java.util.Vector;

public class Sample {
    private List items = new ArrayList();

    public void process() {
        Vector data = new Vector();
        Object o = (foo.bar) items.get(0);
// JADE-FLAG:STRICTER_CAST_CHECKING Complex casts should be reviewed 0.8
        for (int i = 0; i < items.size(); i++) {
            Object o2 = items.get(i);
            data.add(o2);
        }
    }
}
