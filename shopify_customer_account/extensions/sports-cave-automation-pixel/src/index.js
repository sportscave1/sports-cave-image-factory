import {register} from '@shopify/web-pixels-extension';
import {start} from './pixel.mjs';

register(api => start(api));
