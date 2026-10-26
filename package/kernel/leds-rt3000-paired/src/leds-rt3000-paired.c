// SPDX-License-Identifier: GPL-2.0-only
/*
 * RT3000 paired system-status GPIO LEDs.
 * Mirrors the own-C OEM helper's two raw GPIO outputs per software color.
 * The class labels describe software colors, not verified panel lamps.
 */
#include <linux/err.h>
#include <linux/gpio/consumer.h>
#include <linux/leds.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/platform_device.h>

#define RT3000_LED_PAIR_SIZE 2

struct rt3000_leds;

struct rt3000_pair {
	struct led_classdev cdev;
	struct rt3000_leds *owner;
	struct gpio_desc *gpio[RT3000_LED_PAIR_SIZE];
};

struct rt3000_leds {
	struct device *dev;
	struct mutex lock;
	struct rt3000_pair green;
	struct rt3000_pair red;
};

static int rt3000_pair_write_raw(struct rt3000_pair *pair, int raw)
{
	int first_error = 0;
	unsigned int i;

	for (i = 0; i < RT3000_LED_PAIR_SIZE; i++) {
		int ret = gpiod_direction_output_raw(pair->gpio[i], raw);

		if (ret && !first_error)
			first_error = ret;
	}
	return first_error;
}

static int rt3000_pair_set(struct led_classdev *cdev,
			   enum led_brightness brightness)
{
	struct rt3000_pair *pair = container_of(cdev, struct rt3000_pair, cdev);
	struct rt3000_leds *owner = pair->owner;
	int raw = brightness == LED_OFF ? 0 : 1;
	int ret;

	/* Match OEM _raw behavior: every nonzero class brightness means raw 1. */
	mutex_lock(&owner->lock);
	ret = rt3000_pair_write_raw(pair, raw);
	mutex_unlock(&owner->lock);

	if (ret)
		dev_err_ratelimited(owner->dev,
			"failed to set %s GPIO pair: %d\n", cdev->name, ret);
	return ret;
}

static int rt3000_get_pair(struct device *dev, const char *id,
			   struct rt3000_pair *pair)
{
	unsigned int i;

	for (i = 0; i < RT3000_LED_PAIR_SIZE; i++) {
		pair->gpio[i] = devm_gpiod_get_index(dev, id, i, GPIOD_ASIS);
		if (IS_ERR(pair->gpio[i])) {
			int ret = PTR_ERR(pair->gpio[i]);

			dev_err(dev, "cannot acquire %s GPIO %u: %d\n",
				id, i, ret);
			return ret;
		}
	}
	return 0;
}

static int rt3000_pair_register(struct rt3000_leds *owner,
				struct rt3000_pair *pair, const char *id,
				const char *name)
{
	char property[32];
	const char *trigger;
	int ret;

	pair->owner = owner;
	pair->cdev.name = name;
	pair->cdev.max_brightness = LED_FULL;
	pair->cdev.brightness = LED_OFF;
	pair->cdev.brightness_set_blocking = rt3000_pair_set;

	snprintf(property, sizeof(property), "%s-default-trigger", id);
	ret = of_property_read_string(owner->dev->of_node, property, &trigger);
	if (!ret)
		pair->cdev.default_trigger = trigger;
	else if (ret != -EINVAL && ret != -ENODATA) {
		dev_err(owner->dev, "invalid %s property: %d\n", property, ret);
		return ret;
	}

	return devm_led_classdev_register(owner->dev, &pair->cdev);
}

static void rt3000_best_effort_off(struct rt3000_leds *owner)
{
	int green_ret, red_ret;

	green_ret = rt3000_pair_write_raw(&owner->green, 0);
	red_ret = rt3000_pair_write_raw(&owner->red, 0);
	if (green_ret || red_ret)
		dev_err(owner->dev,
			"startup-off recovery incomplete (green=%d red=%d)\n",
			green_ret, red_ret);
}

static int rt3000_leds_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct rt3000_leds *owner;
	int green_ret, red_ret, ret;

	/* This compatible is specific to the RT3000 board, not IPQ5018 alone. */
	if (!of_machine_is_compatible("h3c,rt3000-rtl8367s") ||
	    !of_machine_is_compatible("qcom,ipq5018"))
		return -ENODEV;

	owner = devm_kzalloc(dev, sizeof(*owner), GFP_KERNEL);
	if (!owner)
		return -ENOMEM;
	owner->dev = dev;
	mutex_init(&owner->lock);
	platform_set_drvdata(pdev, owner);

	ret = rt3000_get_pair(dev, "green", &owner->green);
	if (ret)
		return ret;
	ret = rt3000_get_pair(dev, "red", &owner->red);
	if (ret)
		return ret;
	owner->green.owner = owner;
	owner->red.owner = owner;

	/* Explicit startup state: write OEM-deasserted raw 0 to all four lines. */
	mutex_lock(&owner->lock);
	green_ret = rt3000_pair_write_raw(&owner->green, 0);
	red_ret = rt3000_pair_write_raw(&owner->red, 0);
	mutex_unlock(&owner->lock);
	if (green_ret || red_ret) {
		dev_err(dev, "startup-off initialization failed (green=%d red=%d)\n",
			green_ret, red_ret);
		rt3000_best_effort_off(owner);
		return green_ret ? green_ret : red_ret;
	}

	ret = rt3000_pair_register(owner, &owner->green, "green",
				   "rt3000:green:system");
	if (ret)
		return ret;
	return rt3000_pair_register(owner, &owner->red, "red",
				    "rt3000:red:system");
}

static const struct of_device_id rt3000_leds_of_match[] = {
	{ .compatible = "h3c,rt3000-paired-sysleds" },
	{ }
};
MODULE_DEVICE_TABLE(of, rt3000_leds_of_match);

static struct platform_driver rt3000_leds_driver = {
	.probe = rt3000_leds_probe,
	.driver = {
		.name = "rt3000-paired-sysleds",
		.of_match_table = rt3000_leds_of_match,
	},
};
module_platform_driver(rt3000_leds_driver);

MODULE_AUTHOR("OpenAI Codex proposal");
MODULE_DESCRIPTION("RT3000 paired status LED proposal");
MODULE_LICENSE("GPL");
