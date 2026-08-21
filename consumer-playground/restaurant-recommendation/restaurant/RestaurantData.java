package restaurant;

import java.io.Serializable;
import java.util.Map;

public class RestaurantData implements Serializable {
    private final String name;
    private final Map<String, Double> menu;
    private final Map<String, Object> additionalInfo;

    public RestaurantData(String name, Map<String, Double> menu, Map<String, Object> additionalInfo) {
        this.name = name;
        this.menu = menu;
        this.additionalInfo = additionalInfo;
    }

    public String getName() { return name; }
    public Map<String, Double> getMenu() { return menu; }
    public Map<String, Object> getAdditionalInfo() { return additionalInfo; }
}
