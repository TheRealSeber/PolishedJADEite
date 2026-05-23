import java.util.ArrayList;
import java.util.List;
import java.util.Vector;

public class Sample {
    private List items = new ArrayList();

    public void process() {
        Vector data = new Vector();
        for (int i = 0; i < items.size(); i++) {
            Object o = items.get(i);
            data.add(o);
        }
    }
}
